import random
import time
from datetime import datetime, timezone

from confluent_kafka import Producer

from common.logger import log
from robot_dataset import RobotDataset

logger = log("KafkaConsumer")


class KafkaProducer:
    def __init__(self, bootstrap_servers, topic_name):
        # TODO: Verificar quais configurações adequadas para o kafka.
        # Tenho alguns artigos sobre isso.
        # Verificar também o broker.

        producer_config = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": f"{topic_name}-producer",
        }
        self.producer = Producer(producer_config)
        self.topic_name = topic_name

    def produce(self, data_type: str):
        if data_type == "control_power":
            self._produce_control_power_data()
        elif data_type == "accelerometer_gyro":
            self._produce_temperature_accelerometer_gyro_data()
        elif data_type == "mocked":
            self._produce_mocked_data()
        else:
            logger.error(f"Invalid data type ({data_type}) for producer.")

    def _produce_control_power_data(self):
        dataset = RobotDataset(normalize=False)
        dataset = dataset.get_dataset(data_type="control_power")
        self._send_dataset(dataset)

    def _produce_temperature_accelerometer_gyro_data(self):
        dataset = RobotDataset(normalize=False)
        dataset = dataset.get_dataset(data_type="accelerometer_gyro")
        self._send_dataset(dataset)

    def _send_dataset(self, dataset):
        for i in range(len(dataset)):
            timestamp = datetime.now(timezone.utc).isoformat()
            row = dataset.iloc[i, :]
            row["source_timestamp"] = timestamp
            message = row.to_json()
            self._send_message(key=timestamp, value=message)
            time.sleep(0.1)  # 10Hz

    def _produce_mocked_data(self):
        i = 0
        msg_count = 10000
        while i <= msg_count:
            # Creates random temperature data between 20.0
            # and 30.0 degrees Celsius.
            temperature = round(random.uniform(20.0, 30.0), 2)

            timestamp = datetime.now(timezone.utc).isoformat()
            message = f"""{
                {"source_timestamp": {timestamp}, "temperature": {temperature}}
            }"""

            self._send_message(key=timestamp, value=message)
            i += 1
            time.sleep(0.1)  # 10Hz

    def _send_message(self, key, value):
        self.producer.produce(
            self.topic_name,
            key=key,
            value=value,
            callback=self._delivery_report,
        )
        logger.info(f"Message sent: {value}")
        self.producer.flush()

    def _delivery_report(self, err, msg):
        """Delivery callback confirmation."""
        if err is not None:
            logger.error(f"Error in delivery: {err}")
        else:
            logger.info(
                f"Mensagem entregue para {msg.topic()} [{msg.partition()}]"
            )
