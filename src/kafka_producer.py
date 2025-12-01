import os
import random
import threading
import time
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
            "linger.ms": 0,
            "batch.num.messages": 1,
            "compression.type": "none",
            "max.in.flight.requests.per.connection": 1,
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

        threads = []
        for i in range(num_robots):
            thread = threading.Thread(
                target=self._run_simulation, args=(data_type, i)
            )
            threads.append(thread)
            thread.start()
            logger.info(f"Started simulation for robot {i}")

        for thread in threads:
            thread.join()

    def _run_simulation(self, data_type: str, robot_id: int):
        """
        Runs the simulation for a single robot.

        Args:
            data_type (str): Type of data to produce.
            robot_id (int): ID of the robot.
        """
        if data_type == "control_power":
            self._produce_control_power_data(robot_id)
        elif data_type == "accelerometer_gyro":
            self._produce_temperature_accelerometer_gyro_data(robot_id)
        elif data_type == "mocked":
            self._produce_mocked_data(robot_id)
        else:
            logger.error(f"Invalid data type ({data_type}) for producer.")

    def _produce_control_power_data(self, robot_id: int):
        """
        Produces control power data for a specific robot.

        Args:
            robot_id (int): ID of the robot.
        """
        producer = self.get_producer(self.topic_name)
        dataset = RobotDataset(normalize=False)
        dataset = dataset.get_dataset(data_type="control_power")
        self._send_dataset(producer, dataset, robot_id)

    def _produce_temperature_accelerometer_gyro_data(self, robot_id: int):
        """
        Produces accelerometer and gyro data for a specific robot.

        Args:
            robot_id (int): ID of the robot.
        """
        producer = self.get_producer(self.topic_name)
        dataset = RobotDataset(normalize=False)
        dataset = dataset.get_dataset(data_type="accelerometer_gyro")
        self._send_dataset(producer, dataset, robot_id)

    def _send_dataset(self, producer, dataset, robot_id: int):
        """
        Sends the dataset to Kafka.

        Args:
            producer (SerializingProducer): Kafka producer instance.
            dataset (pd.DataFrame): Dataset to send.
            robot_id (int): ID of the robot.
        """
        for i in range(len(dataset)):
            timestamp = datetime.now(UTC).isoformat()
            row = dataset.iloc[i, :]
            row["source_timestamp"] = timestamp
            # Ideally we would add robot_id to the message, but schema might
            # not support it.
            # For now, we just simulate the load.
            message = row.to_dict()
            self._send_message(producer, key=timestamp, value=message)
            time.sleep(0.1)  # 10Hz

    def _send_message(self, producer, key, value):
        """
        Sends a single message to Kafka.

        Args:
            producer (SerializingProducer): Kafka producer instance.
            key (str): Message key.
            value (dict): Message value.
        """
        producer.produce(
            self.topic_name,
            key=str(key),
            value=value,
            on_delivery=self._delivery_report,
        )
        # logger.info(f"Message sent: {value}") # Reduced logging for high freq

    def _delivery_report(self, err, msg):
        """
        Delivery callback confirmation.

        Args:
            err (KafkaError): Error object if delivery failed.
            msg (Message): Kafka message object.
        """
        if err is not None:
            logger.error(f"Error in delivery: {err}")
        # else:
        # logger.info(
        #     f"Mensagem entregue para {msg.topic()} [{msg.partition()}]"
        # )

    def _produce_mocked_data(self, robot_id: int):
        """
        Produces mocked temperature data.

        Args:
            robot_id (int): ID of the robot.
        """
        i = 0
        msg_count = 10000
        producer = self.get_producer(self.topic_name)
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

            self._send_message(producer, key=timestamp, value=message)
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
