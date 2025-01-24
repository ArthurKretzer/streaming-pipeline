import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, from_json
from pyspark.sql.types import DoubleType, StringType, StructType


class KafkaConsumer:
    def __init__(self):
        os.environ["PYSPARK_SUBMIT_ARGS"] = (
            "--packages org.apache.hadoop:hadoop-aws:3.3.4,io.delta:delta-spark_2.12:3.3.0,org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.4,org.apache.kafka:kafka-clients:3.9.0 pyspark-shell"
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

    def create_delta_table(self):
        # Define the schema for the processed table
        processed_schema = (
            StructType()
            .add("timestamp", StringType())
            .add("temperature", DoubleType())
        )

        # Create an empty DataFrame with the schema
        empty_processed_df = self.spark.createDataFrame([], processed_schema)

        # Write the empty DataFrame to create the Delta table with CDF enabled
        empty_processed_df.write.format("delta").option(
            "path", "s3a://lakehouse/delta/raw_iot_data"
        ).option("delta.enableChangeDataFeed", "true").mode("overwrite").save()

    def consume(self):
        # Kafka Configuration
        kafka_broker = "kafka-cpc.certi.org.br:31289"
        topic_name = "iot-temperature"

        # Define the schema for the JSON data
        schema = (
            StructType()
            .add("timestamp", StringType())
            .add("temperature", DoubleType())
        )

        # Read data from Kafka
        kafka_stream = (
            self.spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", kafka_broker)
            .option("subscribe", topic_name)
            .option("startingOffsets", "earliest")
            .load()
        )

        # Deserialize Kafka value (JSON string) into columns
        parsed_stream = (
            kafka_stream.selectExpr("CAST(value AS STRING)")
            .select(from_json(col("value"), schema).alias("data"))
            .select("data.*")
        )

        parsed_stream_with_timestamp = parsed_stream.withColumn(
            "landing_timestamp", current_timestamp()
        )

        # Output the parsed stream for verification
        parsed_stream_with_timestamp.printSchema()

        # Define the path to the raw Delta table
        raw_delta_path = "s3a://lakehouse/delta/raw_iot_data"

        # Write Kafka stream to Delta table
        raw_stream_query = (
            parsed_stream_with_timestamp.writeStream.format("delta")
            .option(
                "checkpointLocation",
                "s3a://lakehouse/delta/checkpoints/raw_iot_data",
            )
            .option("mergeSchema", "true")
            .outputMode("append")
            .start(raw_delta_path)
        )

        print("Streaming Kafka data into Delta Lake (raw_iot_data)...")

        return raw_stream_query
