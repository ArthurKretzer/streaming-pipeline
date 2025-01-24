import sys
import time

from src.data_process import DataProcess
from src.kafka_consumer import KafkaConsumer
from src.kafka_producer import KafkaProducer


def consume():
    consumer = KafkaConsumer()
    consumer.create_delta_table()
    stream = consumer.consume()

    while stream.isActive:
        print(stream.lastProgress)  # Shows the latest progress info
        time.sleep(5)  # Updates every 5 seconds


def produce():
    # Configuração do Kafka
    kafka_broker = (
        "kafka-cpc.certi.org.br:31289"  # Use o serviço bootstrap do Kafka
    )
    topic_name = "iot-temperature"
    producer = KafkaProducer(kafka_broker, topic_name)
    producer.produce()


def process():
    process = DataProcess()
    stream = process.process()

    while stream.isActive:
        print(stream.lastProgress)  # Shows the latest progress info
        time.sleep(5)  # Updates every 5 seconds


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <function_name>")
        sys.exit(1)

    function_name = sys.argv[1]

    if function_name == "consume":
        consume()
    elif function_name == "produce":
        produce()
    elif function_name == "process":
        process()
    else:
        print(
            "Invalid function name. Choose from 'consume', 'produce', or 'process'."
        )
