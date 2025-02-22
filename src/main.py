import os
import time
import traceback
from argparse import ArgumentParser

from dotenv import load_dotenv

from common.logger import log
from data_process import DataProcess
from kafka_consumer import KafkaConsumer
from kafka_consumer_avro import KafkaConsumerAvro
from kafka_producer import KafkaProducer
from kafka_producer_avro import KafkaProducerAvro

load_dotenv()


logger = log("Main")

KAFKA_BROKER = os.getenv("KAFKA_BROKER")


def produce(topic_name: str = "robot", data_type: str = "mocked"):
    topic_name = f"{topic_name}-json"
    try:
        producer = KafkaProducer(KAFKA_BROKER, topic_name)
        producer.produce(data_type)
        logger.info(
            f"Produced data of type '{data_type}' to topic '{topic_name}'."
        )
    except Exception as e:
        logger.error(f"Failed to produce to topic '{topic_name}': {e}")
        traceback.print_exc()


def produce_avro(topic_name: str = "robot", data_type: str = "mocked"):
    topic_name = f"{topic_name}-avro"
    try:
        producer = KafkaProducerAvro(KAFKA_BROKER, topic_name)
        producer.produce(data_type)
        logger.info(
            f"Produced data of type '{data_type}' to topic '{topic_name}'."
        )
    except Exception as e:
        logger.error(f"Failed to produce to topic '{topic_name}': {e}")
        traceback.print_exc()


def consume(topic_name: str = "robot"):
    topic_name = f"{topic_name}-json"
    try:
        consumer = KafkaConsumer(KAFKA_BROKER, topic_name)
        stream = consumer.consume()
        show_stream_progress(stream)
    except Exception as e:
        logger.error(f"Failed to consume from topic '{topic_name}': {e}")
        traceback.print_exc()


def consume_avro(topic_name: str = "robot"):
    topic_name = f"{topic_name}-avro"
    try:
        consumer = KafkaConsumerAvro(KAFKA_BROKER, topic_name)
        stream = consumer.consume()
        show_stream_progress(stream)
    except Exception as e:
        logger.error(f"Failed to consume from topic '{topic_name}': {e}")
        traceback.print_exc()


def process():
    try:
        processor = DataProcess()
        stream = processor.process()
        show_stream_progress(stream)
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        traceback.print_exc()


def show_stream_progress(stream):
    try:
        while stream.isActive:
            logger.info(stream.lastProgress)
            time.sleep(5)
        logger.info("Stream is not active anymore")
        logger.info(stream.lastProgress)
    except AttributeError as e:
        logger.error(f"Error accessing stream attributes: {e}")
        traceback.print_exc()


def parse_arguments():
    parser = ArgumentParser(description="Kafka producer/consumer script")
    parser.add_argument(
        "function_name",
        choices=["consume", "produce", "process"],
        help="Function to execute: 'consume', 'produce', or 'process'.",
    )
    parser.add_argument(
        "topic_name",
        choices=["robot", "control_power", "accelerometer_gyro"],
        default="robot",
        help="Kafka topic name (default: 'robot').",
    )
    parser.add_argument(
        "data_type",
        choices=["mocked", "control_power", "accelerometer_gyro"],
        default="mocked",
        help="Data type to produce (default: 'mocked').",
    )
    parser.add_argument(
        "serialization",
        choices=["avro", "json"],
        default="avro",
        help="Data serialization format to produce (default: 'avro').",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    if args.serialization == "json":
        if args.function_name == "consume":
            consume(args.topic_name)
        elif args.function_name == "produce":
            produce(args.topic_name, args.data_type)
        elif args.function_name == "process":
            process()
    elif args.serialization == "avro":
        if args.function_name == "consume":
            consume_avro(args.topic_name)
        elif args.function_name == "produce":
            produce_avro(args.topic_name, args.data_type)
        elif args.function_name == "process":
            process()
