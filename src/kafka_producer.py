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
            "batch.num.messages": 1000,
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

    def produce(self, data_type: str, num_robots: int = 1):
        """
        Produces data to the Kafka topic, simulating multiple robots.

        Args:
            data_type (str): Type of data to produce ('control_power',
                'accelerometer_gyro', 'mocked').
            num_robots (int): Number of robots to simulate concurrently.
        """
        self._configure_topic()

        # Create a single producer instance shared among all threads
        producer = self.get_producer(self.topic_name)

        logger.info("Loading robot dataset...")
        if data_type != "mocked":
            # Load dataset once for all robots, limited to 1 hour at 10Hz
            # (36000 rows)
            dataset_loader = RobotDataset(normalize=False, max_rows=36000)
            df = dataset_loader.get_dataset(data_type=data_type)
            # Convert DataFrame to a list of dicts for faster iteration and reduced memory
            records = df.to_dict("records")
            del df  # Explicitly free the DataFrame memory
        else:
            records = None

        logger.info("Starting robot simulations...")
        threads = []
        for i in range(num_robots):
            thread = threading.Thread(
                target=self._run_simulation,
                args=(data_type, i, producer, records),
            )
            threads.append(thread)
            thread.start()
            logger.info(f"Started simulation for robot {i}")

        for thread in threads:
            thread.join()

    def _run_simulation(
        self, data_type: str, robot_id: int, producer, records=None
    ):
        """
        Runs the simulation for a single robot.

        Args:
            data_type (str): Type of data to produce.
            robot_id (int): ID of the robot.
            producer (SerializingProducer): Shared Kafka producer instance.
            records (list[dict], optional): Pre-loaded dataset records.
        """
        if data_type == "control_power":
            self._produce_control_power_data(robot_id, producer, records)
        elif data_type == "accelerometer_gyro":
            self._produce_temperature_accelerometer_gyro_data(
                robot_id, producer, records
            )
        elif data_type == "mocked":
            self._produce_mocked_data(robot_id, producer)
        else:
            logger.error(f"Invalid data type ({data_type}) for producer.")

    def _produce_control_power_data(self, robot_id: int, producer, records):
        """
        Produces control power data for a specific robot.

        Args:
            robot_id (int): ID of the robot.
            producer (SerializingProducer): Shared Kafka producer instance.
            records (list[dict]): Dataset records to send.
        """
        self._send_dataset(producer, records, robot_id)

    def _produce_temperature_accelerometer_gyro_data(
        self, robot_id: int, producer, records
    ):
        """
        Produces accelerometer and gyro data for a specific robot.

        Args:
            robot_id (int): ID of the robot.
            producer (SerializingProducer): Shared Kafka producer instance.
            records (list[dict]): Dataset records to send.
        """
        self._send_dataset(producer, records, robot_id)

    def _send_dataset(self, producer, records, robot_id: int):
        """
        Sends the dataset to Kafka.

        Args:
            producer (SerializingProducer): Kafka producer instance.
            records (list[dict]): Dataset records to send.
            robot_id (int): ID of the robot.
        """
        for row in records:
            timestamp = datetime.now(UTC).isoformat()

            # Create a copy to avoid race conditions if modifying shared dicts (though unique timestamps usually imply copy needed)
            message = row.copy()
            message["source_timestamp"] = timestamp
            message["robot_id"] = robot_id

            # Ideally we would add robot_id to the message, but schema might
            # not support it.
            # For now, we just simulate the load.
            self._send_message(
                producer, key=timestamp, value=message, robot_id=robot_id
            )

            # Serve delivery reports to ensure internal queue doesn't fill up indefinitely
            producer.poll(0)

            time.sleep(0.1)  # 10Hz

        producer.flush()

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
            if len(stats_data["deltas"]) >= 100:
                deltas = stats_data["deltas"]
                avg_time = statistics.mean(deltas)
                median_time = statistics.median(deltas)
                std_dev = statistics.stdev(deltas) if len(deltas) > 1 else 0.0

                logger.info(
                    f"Robot {robot_id} stats (last 100 msgs): "
                    f"Avg: {avg_time:.4f}s, "
                    f"Median: {median_time:.4f}s, "
                    f"StdDev: {std_dev:.4f}s"
                )
                # Reset deltas but keep last_ack_time
                stats_data["deltas"] = []

    def _produce_mocked_data(self, robot_id: int, producer):
        """
        Produces mocked temperature data.

        Args:
            robot_id (int): ID of the robot.
            producer (SerializingProducer): Shared Kafka producer instance.
        """
        i = 0
        msg_count = 10000
        while i <= msg_count:
            # Creates random temperature data between 20.0
            # and 30.0 degrees Celsius.
            temperature = round(random.uniform(20.0, 30.0), 2)

            timestamp = int(
                datetime.now(UTC).timestamp() * 1000
            )  # Convert to milliseconds
            message = {
                "source_timestamp": timestamp,
                "temperature": temperature,
            }

            self._send_message(
                producer, key=timestamp, value=message, robot_id=robot_id
            )
            producer.poll(0)
            i += 1
            time.sleep(0.1)  # 10Hz
        producer.flush()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    KafkaProducer(
        bootstrap_servers=os.getenv("KAFKA_BROKER"),
        topic_name="mocked-data",
    ).produce("mocked", num_robots=1)
