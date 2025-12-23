import os
import traceback

from confluent_kafka.admin import AdminClient, ConfigResource, NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient, Schema

from common.logger import log

logger = log("KafkaTopicConfigurator")


class KafkaTopicConfigurator:
    def __init__(
        self, bootstrap_servers: str, schema_registry_url: str = None
    ):
        """
        Initializes the KafkaTopicConfigurator.

        Args:
            bootstrap_servers (str): Kafka broker(s) address.
            schema_registry_url (str, optional): Schema Registry URL.
        """
        self.admin_client = AdminClient(
            {"bootstrap.servers": bootstrap_servers}
        )
        self.schema_registry_url = schema_registry_url

    def topic_exists(self, topic_name: str) -> bool:
        """
        Checks if a topic exists.

        Args:
            topic_name (str): Name of the topic to check.

        Returns:
            bool: True if the topic exists, False otherwise.
        """
        metadata = self.admin_client.list_topics(timeout=10)
        return topic_name in metadata.topics

    def create_topic(
        self,
        topic_name: str,
        num_partitions: int = 15,
        replication_factor: int = 3,
    ) -> bool:
        """
        Creates a Kafka topic if it does not already exist.

        Args:
            topic_name (str): Name of the topic to create.
            num_partitions (int): Number of partitions for the topic.
                Broker default is 15.
            replication_factor (int): Replication factor for the topic.
                Broker default is 3.

        Returns:
            bool: Created (true) or not (false).
        """
        new_topic = NewTopic(
            topic=topic_name,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
        )

        future = self.admin_client.create_topics([new_topic])

        for topic, f in future.items():
            try:
                f.result()  # Wait for the operation to complete
                logger.info(f"Successfully created topic '{topic}'")
                return True
            except Exception as e:
                logger.error(f"Failed to create topic '{topic}': {e}")
                traceback.print_exc()
                return False

    def configure_topic(self, topic_name: str, config_updates: dict) -> None:
        """
        Configures a Kafka topic with the given settings.

        Args:
            topic_name (str): Name of the topic to configure.
            config_updates (dict): Key-value pairs of configuration
                updates (e.g., {'message.timestamp.type': 'LogAppendTime'}).

        Returns:
            str: Success or failure message.
        """
        # Check if the topic exists
        if not self.topic_exists(topic_name):
            logger.warning(
                f"Topic '{topic_name}' does not exist. Creating it..."
            )
            creation_result = self.create_topic(topic_name, num_partitions=4)
            logger.warning(f"Topic creation result: {creation_result}")

        # Create a ConfigResource for the topic
        config_resource = ConfigResource(
            ConfigResource.Type.TOPIC, topic_name, set_config=config_updates
        )

        # Alter the topic configuration
        future = self.admin_client.alter_configs([config_resource])

        # Process the result
        for config, f in future.items():
            try:
                f.result()  # Wait for the operation to complete
                logger.info(
                    "Successfully updated configuration for topic "
                    f"'{config.name}'"
                )
            except Exception as e:
                logger.error(
                    "Failed to update configuration for topic "
                    f"'{config.name}': {e}"
                )
                traceback.print_exc()
                raise

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
        # Determine the absolute path to the 'schemas' directory
        # This assumes 'src' is the parent directory of this file
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
            if os.path.exists(schema_path):
                with open(schema_path, "r") as f:
                    return f.read()
            else:
                raise FileNotFoundError(
                    f"Schema file not found at: {schema_path}"
                )

        raise ValueError(f"No schema mapping found for topic: {topic_name}")

    def register_schema(self, topic_name: str) -> None:
        """
        Registers the schema for the given topic.

        Args:
            topic_name (str): Name of the topic.
        """
        if not self.schema_registry_url:
            logger.warning(
                "Schema Registry URL not provided. Skipping registration."
            )
            return

        try:
            schema_str = self._get_schema(topic_name)
            schema_registry_conf = {"url": self.schema_registry_url}
            client = SchemaRegistryClient(schema_registry_conf)

            subject_name = f"{topic_name}-value"
            schema = Schema(schema_str, schema_type="AVRO")

            schema_id = client.register_schema(subject_name, schema)
            logger.info(
                f"Successfully registered schema for subject '{subject_name}' "
                f"with ID: {schema_id}"
            )

        except Exception as e:
            logger.error(
                f"Failed to register schema for topic '{topic_name}': {e}"
            )
            traceback.print_exc()


# Example usage
if __name__ == "__main__":
    # Initialize the configurator with Kafka broker address
    kafka_configurator = KafkaTopicConfigurator(
        bootstrap_servers="localhost:12345"
    )

    # Specify the topic name and configuration updates
    topic_name = "example_topic"
    # Set timestamp type to LogAppendTime
    config_updates = {"message.timestamp.type": "LogAppendTime"}

    # Update the topic configuration
    result = kafka_configurator.configure_topic(topic_name, config_updates)
