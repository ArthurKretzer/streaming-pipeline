import random
import time
from datetime import datetime, timezone

from confluent_kafka import Producer
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("./.env")


class KafkaProducer:
    def __init__(self, bootstrap_servers, topic_name):
        producer_config = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "iot-producer",
        }
        self.producer = Producer(producer_config)
        self.topic_name = topic_name

    def send_message(self, key, value):
        self.producer.produce(
            self.topic_name,
            key=key,
            value=value,
            callback=self.delivery_report,
        )
        self.producer.flush()

    def delivery_report(self, err, msg):
        """Callback de confirmação de entrega."""
        if err is not None:
            print(f"Erro na entrega: {err}")
        else:
            print(f"Mensagem entregue para {msg.topic()} [{msg.partition()}]")

    def produce(self):
        while True:
            # Simula dados do sensor
            temperature = round(random.uniform(20.0, 30.0), 2)
            timestamp = datetime.now(timezone.utc).isoformat()
            message = f"""{
                {"timestamp": {timestamp}, "temperature": {temperature}}
            }"""

            print(f"Message sent: {message}")
            # Envia para o Kafka
            self.producer.produce(
                self.topic_name,
                key=str(time.time()),
                value=message,
                callback=self.delivery_report,
            )
            self.producer.poll(0)

            # Aguarda 1 segundo antes de enviar o próximo dado
            time.sleep(1)
