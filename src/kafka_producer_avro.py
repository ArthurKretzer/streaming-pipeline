import os
import random
import time
from datetime import datetime, timezone

from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import StringSerializer

from common.logger import log
from kafka_topic_configurator import KafkaTopicConfigurator
from robot_dataset import RobotDataset

logger = log("KafkaProducerAvro")


class KafkaProducerAvro:
    def __init__(self, bootstrap_servers, topic_name):
        self.bootstrap_servers = bootstrap_servers
        self.topic_name = topic_name

    def get_producer(self, topic_name: str):
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

    def get_serializers(self, topic_name):
        schema_registry_conf = {"url": "http://kafka-cpc.certi.org.br:32081"}

        schema_registry_client = SchemaRegistryClient(schema_registry_conf)

        value_serializer = AvroSerializer(
            schema_registry_client, self._get_schema(topic_name)
        )

        key_serializer = StringSerializer("utf_8")

        return key_serializer, value_serializer

    def _get_schema(self, topic_name: str):
        if topic_name == "control_power-avro":
            with open("./src/schemas/control_power.json") as f:
                schema = f.read()
            return schema
        elif topic_name == "accelerometer_gyro-avro":
            with open("./src/schemas/accelerometer_gyro.json") as f:
                schema = f.read()
            return schema
        elif topic_name == "mocked-avro":
            with open("./src/schemas/temperature.json") as f:
                schema = f.read()
            return schema
        else:
            logger.error(f"Invalid data type ({topic_name}) for schema.")

    def _configure_topic(self):
        configurator = KafkaTopicConfigurator(self.bootstrap_servers)
        config_updates = {"message.timestamp.type": "LogAppendTime"}
        configurator.configure_topic(self.topic_name, config_updates)

    def _produce_control_power_data(self):
        producer = self.get_producer(self.topic_name)
        dataset = RobotDataset(normalize=False)
        dataset = dataset.get_dataset(data_type="control_power")
        self._send_dataset(producer, dataset)

    def _produce_temperature_accelerometer_gyro_data(self):
        producer = self.get_producer(self.topic_name)
        dataset = RobotDataset(normalize=False)
        dataset = dataset.get_dataset(data_type="accelerometer_gyro")
        self._send_dataset(producer, dataset)

    def _send_dataset(self, producer, dataset):
        for i in range(len(dataset)):
            timestamp = datetime.now(timezone.utc).isoformat()
            row = dataset.iloc[i, :]
            row["source_timestamp"] = timestamp
            message = row.to_dict()
            self._send_message(producer, key=timestamp, value=message)
            time.sleep(0.1)  # 10Hz

    def _send_message(self, producer, key, value):
        producer.produce(
            self.topic_name,
            key=str(key),
            value=value,
            on_delivery=self._delivery_report,
        )
        logger.info(f"Message sent: {value}")
        producer.flush()

    def produce(self, data_type: str):
        self._configure_topic()
        if data_type == "control_power":
            self._produce_control_power_data()
        elif data_type == "accelerometer_gyro":
            self._produce_temperature_accelerometer_gyro_data()
        elif data_type == "mocked":
            self._produce_mocked_data()
        else:
            logger.error(f"Invalid data type ({data_type}) for producer.")

    def _delivery_report(self, err, msg):
        """Delivery callback confirmation."""
        if err is not None:
            logger.error(f"Error in delivery: {err}")
        else:
            logger.info(
                f"Mensagem entregue para {msg.topic()} [{msg.partition()}]"
            )

    def _produce_mocked_data(self):
        i = 0
        msg_count = 10000
        producer = self.get_producer(self.topic_name)
        while i <= msg_count:
            # Creates random temperature data between 20.0
            # and 30.0 degrees Celsius.
            temperature = round(random.uniform(20.0, 30.0), 2)

            timestamp = int(
                datetime.now(timezone.utc).timestamp() * 1000
            )  # Convert to milliseconds
            message = {
                "source_timestamp": timestamp,
                "temperature": temperature,
            }

            self._send_message(producer, key=timestamp, value=message)
            i += 1
            time.sleep(0.1)  # 10Hz


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    KafkaProducerAvro(
        bootstrap_servers=os.getenv("KAFKA_BROKER"),
        topic_name="mocked-data",
    ).produce("mocked")
