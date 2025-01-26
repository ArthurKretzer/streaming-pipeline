import os

from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, from_json
from pyspark.sql.types import (
    DoubleType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from common.logger import log

load_dotenv()
logger = log("KafkaConsumer")


class KafkaConsumer:
    def __init__(
        self, kafka_bootstrap_servers: str, kafka_topic: str = "robot"
    ):
        self.topic_name = kafka_topic
        self.kafka_bootstrap_servers = kafka_bootstrap_servers

        # TODO: Avaliar a utilização de outra ferramenta que não o Spark, como o Storm ou Flink.

        # Set up Spark with Delta Lake and MinIO support
        minio_package = "org.apache.hadoop:hadoop-aws:3.3.4"
        delta_package = "io.delta:delta-spark_2.12:3.3.0"
        kafka_package = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.4"
        kafka_package += ",org.apache.kafka:kafka-clients:3.9.0"
        packages = f"{minio_package},{delta_package},{kafka_package}"

        # Submit packages to Spark
        os.environ["PYSPARK_SUBMIT_ARGS"] = (
            f"--packages {packages} pyspark-shell"
        )

        # Initialize Spark session with Delta Lake and MinIO support
        self.spark = (
            SparkSession.builder.appName("DeltaLakeWithMinIO")
            ## Delta
            .config(
                "spark.sql.extensions",
                "io.delta.sql.DeltaSparkSessionExtension",
            )
            # Hive Catalog
            .config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
            ## Optimize Delta
            .config("delta.autoOptimize.optimizeWrite", "true")
            .config("delta.autoOptimize.autoCompact", "true")
            .config(
                "spark.delta.logStore.class",
                "org.apache.spark.sql.delta.storage.S3SingleDriverLogStore",
            )
            ## MinIO
            .config(
                "spark.hadoop.fs.s3a.endpoint", os.getenv("MINIO_ENDPOINT")
            )
            .config(
                "spark.hadoop.fs.s3a.access.key", os.getenv("MINIO_ACCESS_KEY")
            )
            .config(
                "spark.hadoop.fs.s3a.secret.key", os.getenv("MINIO_SECRET_KEY")
            )
            .config("spark.hadoop.fs.s3a.attempts.maximum", "3")
            .config("spark.hadoop.fs.s3a.connection.timeout", "10000")
            .config("spark.hadoop.fs.s3a.connection.establish.timeout", "5000")
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config(
                "spark.hadoop.fs.s3a.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem",
            )
            .config(
                "spark.hadoop.fs.s3.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem",
            )
            .config(
                "spark.hadoop.fs.s3n.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem",
            )
            .getOrCreate()
        )

    def consume(self):
        # Read data from Kafka
        kafka_stream = (
            self.spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", self.kafka_bootstrap_servers)
            .option("subscribe", self.topic_name)
            .option("startingOffsets", "earliest")
            .load()
        )

        # Preserve original Kafka schema and add landing timestamp
        kafka_stream_with_timestamp = kafka_stream.withColumn(
            "landing_timestamp", current_timestamp()
        )

        # Define the JSON schema dynamically
        json_schema = StructType(
            [
                StructField("robot_action_id", StringType(), True),
                StructField("apparent_power", DoubleType(), True),
                StructField("current", DoubleType(), True),
                StructField("frequency", DoubleType(), True),
                StructField("phase_angle", DoubleType(), True),
                StructField("power", DoubleType(), True),
                StructField("power_factor", DoubleType(), True),
                StructField("reactive_power", DoubleType(), True),
                StructField("voltage", DoubleType(), True),
                StructField(
                    "source_timestamp", TimestampType(), True
                ),  # Epoch timestamp column
            ]
        )

        # Parse the JSON from the `value` column into a structured format
        parsed_stream = (
            kafka_stream_with_timestamp.selectExpr(
                "CAST(key AS STRING)",  # Preserve the Kafka key as a string
                "CAST(value AS STRING)",  # Deserialize the Kafka value into a string
                "topic",
                "partition",
                "offset",
                "timestamp",
                "timestampType",
                "landing_timestamp",
            ).withColumn(
                "parsed_value", from_json(col("value"), json_schema)
            )  # Use provided JSON schema
        )

        # Explode the JSON into individual fields while keeping the original schema
        exploded_stream = parsed_stream.select(
            "key",
            "topic",
            "partition",
            "offset",
            "timestamp",
            "timestampType",
            "landing_timestamp",
            col("parsed_value.*"),  # Expand the JSON into separate columns
        )

        # Output the schema for verification
        exploded_stream.printSchema()

        # Define the path to the raw Delta table
        raw_delta_path = f"s3a://lakehouse/delta/raw_{self.topic_name}"

        # Write Kafka stream to Delta table
        raw_stream_query = (
            exploded_stream.writeStream.format("delta")
            .option(
                "checkpointLocation",
                f"s3a://lakehouse/delta/checkpoints/raw_{self.topic_name}",
            )
            .option("mergeSchema", "true")
            .option("delta.enableChangeDataFeed", "true")
            .outputMode("append")
            .start(raw_delta_path)
        )

        logger.info(
            f"Streaming Kafka data from {self.topic_name} into Delta Lake raw_{self.topic_name}..."
        )

        return raw_stream_query
