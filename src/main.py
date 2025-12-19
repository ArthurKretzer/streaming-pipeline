import os
import time
import threading
import signal
import traceback
from argparse import ArgumentParser

from dotenv import load_dotenv

from common.logger import log
from common.tcpdump_manager import TcpDumpManager
from data_process import DataProcess
from kafka_consumer import KafkaConsumer
from kafka_producer import KafkaProducer

load_dotenv()


logger = log("Main")

KAFKA_BROKER = os.getenv("KAFKA_BROKER")

# TCPDump Configuration
ENABLE_TCPDUMP = os.getenv("ENABLE_TCPDUMP", "False").lower() == "true"
TCPDUMP_INTERFACE = os.getenv("TCPDUMP_INTERFACE", "eth0")
TCPDUMP_OUTPUT_PATH = os.getenv("TCPDUMP_OUTPUT_PATH", "./data")


def produce(
    topic_name: str = "robot",
    data_type: str = "mocked",
    num_robots: int = 1,
    stop_event: threading.Event = None,
):
    """
    Produces data to a Kafka topic.

    Args:
        topic_name (str): The name of the Kafka topic. Defaults to "robot".
        data_type (str): The type of data to produce. Defaults to "mocked".
        num_robots (int): The number of robots to simulate. Defaults to 1.
    """
    topic_name = f"{topic_name}-avro"

    # Extract host from KAFKA_BROKER (remove port if present)
    target_host = KAFKA_BROKER.split(":")[0] if KAFKA_BROKER else "localhost"

    try:
        with TcpDumpManager(
            interface=TCPDUMP_INTERFACE,
            output_path=TCPDUMP_OUTPUT_PATH,
            target_host=target_host,
            enabled=ENABLE_TCPDUMP,
        ):
            logger.info(
                f"Producing data of type '{data_type}' to topic '{topic_name}' "
                f"with {num_robots} robots."
            )
            producer = KafkaProducer(KAFKA_BROKER, topic_name)
            producer.produce(data_type, num_robots, stop_event)
            logger.info(
                f"Produced data of type '{data_type}' to topic '{topic_name}' "
                f"with {num_robots} robots."
            )
    except Exception as e:
        logger.error(f"Failed to produce to topic '{topic_name}': {e}")
        traceback.print_exc()


def consume(topic_name: str = "robot"):
    """
    Consumes data from a Kafka topic.

    Args:
        topic_name (str): The name of the Kafka topic. Defaults to "robot".
    """
    topic_name = f"{topic_name}-avro"
    try:
        consumer = KafkaConsumer(KAFKA_BROKER, topic_name)
        stream = consumer.consume()
        show_stream_progress(stream)
    except Exception as e:
        logger.error(f"Failed to consume from topic '{topic_name}': {e}")
        traceback.print_exc()


def process():
    """
    Processes data using DataProcess.
    """
    try:
        processor = DataProcess()
        stream = processor.process()
        show_stream_progress(stream)
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        traceback.print_exc()


def show_stream_progress(stream):
    """
    Shows the progress of a Spark stream.

    Args:
        stream: The Spark stream object.
    """
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
    """
    Parses command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
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
        "--num-robots",
        type=int,
        default=1,
        help="Number of robots to simulate (default: 1).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    stop_event = threading.Event()

    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, stopping...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info(
        f"Starting {args.function_name} with topic '{args.topic_name}' and data type '{args.data_type}'."
    )
    if args.function_name == "consume":
        consume(args.topic_name)
    elif args.function_name == "produce":
        produce(
            args.topic_name,
            args.data_type,
            args.num_robots,
            stop_event=stop_event,
        )
    elif args.function_name == "process":
        process()
