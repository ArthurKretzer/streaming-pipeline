import json
import os

from confluent_kafka.schema_registry import SchemaRegistryClient
from dotenv import load_dotenv
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

from common.logger import log

load_dotenv()
logger = log("KafkaConsumerAvro")

SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI")


class KafkaConsumerAvro:
    def __init__(
        self, kafka_bootstrap_servers: str, kafka_topic: str = "robot"
    ):
        self.topic_name = kafka_topic
        self.kafka_bootstrap_servers = kafka_bootstrap_servers

        # Set up Spark with Delta Lake and MinIO support
        minio_package = "org.apache.hadoop:hadoop-aws:3.3.4"
        delta_package = "io.delta:delta-spark_2.12:3.3.0"
        kafka_package = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.4"
        kafka_package += ",org.apache.kafka:kafka-clients:3.9.0"
        kafka_package += ",org.apache.spark:spark-avro_2.12:3.5.1"
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
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config("spark.hadoop.fs.s3a.fast.upload", True)
            .config("spark.hadoop.fs.s3a.multipart.size", 104857600)
            .config(
                "spark.hadoop.fs.s3a.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem",
            )
            .config("spark.streaming.concurrentJobs", "5")
            .config("spark.executor.instances", "1")
            .config("spark.executor.cores", "15")
            .config("spark.executor.memory", "12g")
            .config("spark.driver.memory", "6g")
            .getOrCreate()
        )

        self.spark.sparkContext.setLogLevel("WARN")

    def get_spark_schema_from_registry(self, schema_registry_url, topic):
        logger.info("Getting schema from registry")
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

        # raw_stream_query = (
        #     parsed_stream.writeStream.format("console")
        #     .outputMode("append")
        #     .option("truncate", "false")
        #     .trigger(processingTime="1 seconds")
        #     .start()
        # )

        raw_stream_query.explain(True)

        logger.info(
            f"Streaming Kafka data from {self.topic_name} into Delta Lake raw_{self.topic_name}..."
        )

        return raw_stream_query
