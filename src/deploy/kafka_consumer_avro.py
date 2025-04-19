import json
import os
import time
import traceback

from confluent_kafka.schema_registry import SchemaRegistryClient
from pyspark.sql import SparkSession
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.functions import current_timestamp, expr
from pyspark.sql.types import (
    FloatType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI")


class KafkaConsumerAvro:
    def __init__(
        self, kafka_bootstrap_servers: str, kafka_topic: str = "robot"
    ):
        kafka_topic = f"{kafka_topic}-avro"
        self.topic_name = kafka_topic
        self.kafka_bootstrap_servers = kafka_bootstrap_servers

        print(f"Minio endpoint: {os.getenv('MINIO_ENDPOINT')}")
        print(f"Minio access_key: {os.getenv('MINIO_ACCESS_KEY')}")

        # Initialize Spark session with Delta Lake and MinIO support
        self.spark = (
            SparkSession.builder.appName("DeltaLakeWithMinIO")
            .config(
                "spark.hadoop.fs.s3a.access.key", os.getenv("MINIO_ACCESS_KEY")
            )
            .config(
                "spark.hadoop.fs.s3a.secret.key", os.getenv("MINIO_SECRET_KEY")
            )
            .getOrCreate()
        )

        self.spark.sparkContext.setLogLevel("WARN")

    def get_spark_schema_from_registry(self, schema_registry_url, topic):
        print(f"Getting schema from registry: {SCHEMA_REGISTRY_URI}")
        schema_registry_client = SchemaRegistryClient(
            {"url": schema_registry_url}
        )
        schema_id = schema_registry_client.get_latest_version(
            f"{topic}-value"
        ).schema_id
        avro_schema_str = schema_registry_client.get_schema(
            schema_id
        ).schema_str

        # Parse the Avro schema JSON string
        avro_schema = json.loads(avro_schema_str)

        # Convert the Avro schema to Spark StructType
        fields = []
        for field in avro_schema["fields"]:
            field_name = field["name"]
            field_type = field["type"]

            if field_type == "int":
                spark_type = IntegerType()
            elif field_type == "string":
                spark_type = StringType()
            elif field_type == "float":
                spark_type = FloatType()
            else:
                raise ValueError(f"Unsupported field type: {field_type}")

            fields.append(StructField(field_name, spark_type, True))

        return StructType(fields), avro_schema_str

    def consume(self):
        # Read data from Kafka
        # .option("maxOffsetsPerTrigger", 5)  # 5 messages per trigger. 2Hz.
        kafka_stream = (
            self.spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", self.kafka_bootstrap_servers)
            .option("subscribe", self.topic_name)
            .option("startingOffsets", "earliest")
            .option("failOnDataLoss", "false")
            .option("minPartitions", "15")
            .load()
        )

        # Preserve original Kafka schema and add landing timestamp
        kafka_stream_with_timestamp = kafka_stream.withColumn(
            "landing_timestamp", current_timestamp()
        )

        struct_schema, avro_schema_str = self.get_spark_schema_from_registry(
            SCHEMA_REGISTRY_URI, self.topic_name
        )

        # Parse the JSON from the `value` column into a structured format
        parsed_stream = kafka_stream_with_timestamp.select(
            "topic",
            "timestamp",
            "landing_timestamp",
            from_avro(
                expr("substring(value, 6, length(value)-5)"),
                avro_schema_str,
            ).alias("parsed_value"),
        )

        # Output the schema for verification
        parsed_stream.printSchema()

        # Define the path to the raw Delta table
        raw_delta_path = f"s3a://lakehouse/delta/raw_{self.topic_name}"

        # Write Kafka stream to Delta table
        raw_stream_query = (
            parsed_stream.writeStream.format("delta")
            .option(
                "checkpointLocation",
                f"s3a://lakehouse/delta/checkpoints/raw_{self.topic_name}",
            )
            .option(
                "mergeSchema", "false"
            )  # Schema will not evolve, should provide better performance
            .option("delta.enableChangeDataFeed", "false")
            .outputMode("append")
            .option("delta.logRetentionDuration", "interval 1 day")
            .option("delta.checkpointInterval", "5")
            .trigger(processingTime="1 seconds")
            .option("truncate", "false")
            .start(raw_delta_path)
        )

        raw_stream_query.explain(True)

        print(
            f"Streaming Kafka data from {self.topic_name} into Delta Lake raw_{self.topic_name}..."
        )

        return raw_stream_query


def show_stream_progress(stream):
    try:
        while stream.isActive:
            print(stream.lastProgress)
            time.sleep(5)
        print("Stream is not active anymore")
        print(stream.lastProgress)
    except AttributeError as e:
        print(f"Error accessing stream attributes: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kafka-topic",
        type=str,
        required=True,
        help="Kafka topic to consume from",
    )
    args = parser.parse_args()

    consumer = KafkaConsumerAvro(
        kafka_bootstrap_servers="master-kafka-external-bootstrap.ingestion.svc.cluster.local:9094",
        kafka_topic=args.kafka_topic,
    )
    stream_query = consumer.consume()

    show_stream_progress(stream_query)
