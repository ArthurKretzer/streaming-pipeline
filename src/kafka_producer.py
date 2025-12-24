import os
import random
import statistics
import threading
import time
from functools import partial
from datetime import UTC, datetime

from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import StringSerializer

from common.logger import log
from kafka_topic_configurator import KafkaTopicConfigurator
from robot_dataset import RobotDataset

logger = log("KafkaProducer")

SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI")


class KafkaProducer:
    """
    Kafka Producer class to send data to Kafka topics using Avro serialization.

    Attributes:
        bootstrap_servers (str): Kafka bootstrap servers.
        topic_name (str): Name of the Kafka topic.
        producer_config (dict): Configuration for the Kafka producer.
    """

    def __init__(self, bootstrap_servers: str, topic_name: str):
        """
        Initializes the KafkaProducer.

        Args:
            bootstrap_servers (str): Kafka bootstrap servers.
            topic_name (str): Name of the Kafka topic.
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic_name = topic_name
        self.stats_lock = threading.Lock()
        self.robot_stats = {}

    def get_producer(self, topic_name: str) -> SerializingProducer:
        """
        Creates and returns a SerializingProducer instance.

        Args:
            topic_name (str): Name of the Kafka topic.

        Returns:
            SerializingProducer: Configured Kafka producer.
        """
        key_serializer, value_serializer = self.get_serializers(topic_name)

        self.producer_config = {
            "bootstrap.servers": self.bootstrap_servers,
            "key.serializer": key_serializer,
            "value.serializer": value_serializer,
            "client.id": f"{self.topic_name}-producer",
            "acks": 1,
            "enable.idempotence": False,
            "linger.ms": 10,
            "batch.num.messages": 10000,
            "queue.buffering.max.messages": 500000,
            "compression.type": "none",
            "max.in.flight.requests.per.connection": 5,
        }

        producer = SerializingProducer(self.producer_config)

        return producer

    def get_serializers(self, topic_name: str):
        """
        Gets the key and value serializers for the producer.

        Args:
            topic_name (str): Name of the Kafka topic.

        Returns:
            tuple: Key and value serializers.
        """
        schema_registry_conf = {"url": SCHEMA_REGISTRY_URI}

        schema_registry_client = SchemaRegistryClient(schema_registry_conf)

        value_serializer = AvroSerializer(
            schema_registry_client, self._get_schema(topic_name)
        )

        key_serializer = StringSerializer("utf_8")

        return key_serializer, value_serializer

    def _get_schema(self, topic_name: str) -> str:
        """
        Retrieves the Avro schema for the specified topic.

        Args:
            topic_name (str): Name of the Kafka topic.

        Returns:
            str: Avro schema as a string.

        Raises:
            ValueError: If no schema is found for the topic.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        schema_dir = os.path.join(current_dir, "schemas")

        schema_mapping = {
            "control_power-avro": "control_power.json",
            "accelerometer_gyro-avro": "accelerometer_gyro.json",
            "mocked-avro": "temperature.json",
            "robot_data-avro": "robot_data.json",
        }

        if topic_name in schema_mapping:
            schema_path = os.path.join(schema_dir, schema_mapping[topic_name])
            with open(schema_path) as f:
                return f.read()

        raise ValueError(f"No schema found for topic: {topic_name}")

    def _configure_topic(self):
        """
        Configures the Kafka topic with specific settings.
        """
        configurator = KafkaTopicConfigurator(self.bootstrap_servers)
        config_updates = {"message.timestamp.type": "LogAppendTime"}
        configurator.configure_topic(self.topic_name, config_updates)

    def produce(
        self,
        data_type: str,
        num_robots: int = 1,
        frequency: int = 10,
        stop_event=None,
    ):
        """
        Produces data to the Kafka topic, simulating multiple robots.

        Args:
            data_type (str): Type of data to produce ('control_power',
                'accelerometer_gyro', 'mocked').
            num_robots (int): Number of robots to simulate concurrently.
            frequency (int): Frequency in Hz.
            stop_event (threading.Event): Event to signal stopping.
        """
        self._configure_topic()

        # Create a single producer instance shared among all threads
        producer = self.get_producer(self.topic_name)

        logger.info("Loading robot dataset...")
        if data_type != "mocked":
            # Load dataset once for all robots, limited to 1 hour at {frequency}Hz
            # ({frequency * 3600} rows)
            max_rows = frequency * 3600
            dataset_loader = RobotDataset(normalize=False, max_rows=max_rows)
            df = dataset_loader.get_dataset(data_type=data_type)
            # Convert DataFrame to a list of dicts for faster iteration and reduced memory
            records = df.to_dict("records")
            del df  # Explicitly free the DataFrame memory
        else:
            records = None

        # Start polling thread
        self.polling_active = True
        self.polling_thread = threading.Thread(
            target=self.poll_scheduler, args=(producer,)
        )
        self.polling_thread.start()

        # Determine number of worker threads based on CPU cores
        # We want to avoid excessive context switching with 100 threads.
        # Using ~1 thread per core is usually optimal for CPU/GIL bound tasks.
        num_workers = min(os.cpu_count() or 4, num_robots)
        logger.info(
            f"Starting {num_robots} robot simulations using {num_workers} "
            "worker threads..."
        )

        threads = []
        robots_per_worker = num_robots // num_workers
        remainder = num_robots % num_workers

        start_robot_id = 0
        for i in range(num_workers):
            # Distribute remainder among the first few workers
            count = robots_per_worker + (1 if i < remainder else 0)
            robot_ids = list(range(start_robot_id, start_robot_id + count))
            start_robot_id += count

            if not robot_ids:
                continue

            thread = threading.Thread(
                target=self._run_worker,
                args=(
                    data_type,
                    robot_ids,
                    producer,
                    records,
                    frequency,
                    stop_event,
                ),
            )
            threads.append(thread)
            thread.start()
            logger.info(
                f"Started worker {i} managing robots: "
                f"{robot_ids[0]}..{robot_ids[-1]}"
            )

        for thread in threads:
            thread.join()

        # Stop polling thread
        self.polling_active = False
        self.polling_thread.join()

    def _run_worker(
        self,
        data_type: str,
        robot_ids: list[int],
        producer,
        records=None,
        frequency: int = 10,
        stop_event=None,
    ):
        """
        Runs the simulation for a batch of robots.
        Iterates through all assigned robots for each time step.
        """
        period = 1.0 / frequency

        if data_type == "mocked":
            i = 0
            while not (stop_event and stop_event.is_set()):
                t_start = time.time()
                for robot_id in robot_ids:
                    # Creates random temperature data
                    temperature = round(random.uniform(20.0, 30.0), 2)
                    timestamp = int(datetime.now(UTC).timestamp() * 1000)
                    message = {
                        "source_timestamp": timestamp,
                        "temperature": temperature,
                    }
                    self._send_message(
                        producer,
                        key=timestamp,
                        value=message,
                        robot_id=robot_id,
                    )

                i += 1
                t_elapsed = time.time() - t_start
                sleep_time = max(0, period - t_elapsed)
                time.sleep(sleep_time)

        else:
            # Dataset playback
            # We iterate the dataset indefinitely or until it ends?
            # Original code iterated once through 'records'.
            for row in records:
                if stop_event and stop_event.is_set():
                    break

                t_start = time.time()

                for robot_id in robot_ids:
                    # Create a copy to avoid race conditions
                    # (though strictly we are reading, copy adds robot_id)
                    current_timestamp = datetime.now(UTC).isoformat()
                    message = row.copy()
                    message["source_timestamp"] = current_timestamp
                    message["robot_id"] = robot_id

                    self._send_message(
                        producer,
                        key=current_timestamp,
                        value=message,
                        robot_id=robot_id,
                    )

                t_elapsed = time.time() - t_start
                sleep_time = max(0, period - t_elapsed)
                time.sleep(sleep_time)

        producer.flush()

    def poll_scheduler(self, producer):
        """
        Continuously polls the producer to trigger delivery reports.
        """
        while self.polling_active:
            producer.poll(0.1)

    def _send_message(self, producer, key, value, robot_id=None):
        """
        Sends a single message to Kafka.

        Args:
            producer (SerializingProducer): Kafka producer instance.
            key (str): Message key.
            value (dict): Message value.
            robot_id (int, optional): ID of the robot for stats.
        """
        callback = (
            partial(self._delivery_report, robot_id=robot_id)
            if robot_id is not None
            else self._delivery_report
        )

        while True:
            try:
                producer.produce(
                    self.topic_name,
                    key=str(key),
                    value=value,
                    on_delivery=callback,
                )
                break
            except BufferError:
                # If the queue is full, poll to clear sending queue and retry
                producer.poll(0.1)
        # logger.info(f"Message sent: {value}") # Reduced logging for high freq

    def _delivery_report(self, err, msg, robot_id=None):
        """
        Delivery callback confirmation with stats logging.

        Args:
            err (KafkaError): Error object if delivery failed.
            msg (Message): Kafka message object.
            robot_id (int, optional): Robot ID to track stats.
        """
        if err is not None:
            logger.error(f"Error in delivery: {err}")
            return

        if robot_id is None:
            return

        current_time = time.time()
        with self.stats_lock:
            if robot_id not in self.robot_stats:
                self.robot_stats[robot_id] = {
                    "last_ack_time": None,
                    "deltas": [],
                    "count": 0,
                }

            stats_data = self.robot_stats[robot_id]
            stats_data["count"] += 1

            if stats_data["last_ack_time"] is not None:
                delta = current_time - stats_data["last_ack_time"]
                stats_data["deltas"].append(delta)

            stats_data["last_ack_time"] = current_time

            # Log every 100 messages
            # if len(stats_data["deltas"]) >= 100:
            #     deltas = stats_data["deltas"]
            #     avg_time = statistics.mean(deltas)
            #     median_time = statistics.median(deltas)
            #     std_dev = statistics.stdev(deltas) if len(deltas) > 1 else 0.0

            #     logger.info(
            #         f"Robot {robot_id} stats (last 100 msgs): "
            #         f"Avg: {avg_time:.4f}s, "
            #         f"Median: {median_time:.4f}s, "
            #         f"StdDev: {std_dev:.4f}s"
            #     )
            #     # Reset deltas but keep last_ack_time
            #     stats_data["deltas"] = []


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    KafkaProducer(
        bootstrap_servers=os.getenv("KAFKA_BROKER"),
        topic_name="mocked-data",
    ).produce("mocked", num_robots=1)
