import traceback

from confluent_kafka.admin import AdminClient, ConfigResource, NewTopic

from common.logger import log

logger = log("KafkaTopicConfigurator")


class KafkaTopicConfigurator:
    def __init__(self, bootstrap_servers: str):
        """
        Initializes the KafkaTopicConfigurator with the given bootstrap
        servers.

        Args:
            bootstrap_servers (str): Kafka broker(s) address
                (e.g., 'localhost:9092').
        """
        self.admin_client = AdminClient(
            {"bootstrap.servers": bootstrap_servers}
        )

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
