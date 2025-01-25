import sys
import time

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from common.logger import log
from data_process import DataProcess
from kafka_consumer import KafkaConsumer
from kafka_producer import KafkaProducer

logger = log("Main")

kafka_broker = "kafka-cpc.certi.org.br:31289"  # Kafka Bootstrap server


def produce(topic_name: str = "robot", data_type: str = "mocked"):
    producer = KafkaProducer(kafka_broker, topic_name)
    producer.produce(data_type)


def consume(topic_name: str = "robot"):
    consumer = KafkaConsumer(kafka_broker, topic_name)
    stream = consumer.consume()

    show_stream_progress(stream)


def process():
    process = DataProcess()
    stream = process.process()

    show_stream_progress(stream)


def show_stream_progress(stream):
    while stream.isActive:
        logger.info(stream.lastProgress)
        time.sleep(5)
    logger.info("Stream is not active anymore")
    logger.info(stream.lastProgress)


if __name__ == "__main__":
    if (len(sys.argv) < 2) | (len(sys.argv) > 3):
        logger.error("Usage: python script.py <function_name> <topic_name>")
        sys.exit(1)

    function_name = sys.argv[1]

    try:
        topic_name = sys.argv[2]
    except IndexError:
        pass

    if function_name == "consume":
        consume(topic_name)
    elif function_name == "produce":
        produce(topic_name, "mocked")
    elif function_name == "process":
        process()
    else:
        logger.error(
            "Invalid function name. Choose from 'consume', 'produce', or 'process'."
        )
