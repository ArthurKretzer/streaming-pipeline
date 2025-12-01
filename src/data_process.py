import os

from pyspark.sql import SparkSession


class DataProcess:
    def __init__(self):
        os.environ["PYSPARK_SUBMIT_ARGS"] = (
            "--packages org.apache.hadoop:hadoop-aws:3.3.4,"
            "io.delta:delta-spark_2.12:3.3.0 pyspark-shell"
        )

        self.spark = (
            SparkSession.builder.appName("DeltaLakeWithMinIO")
            .config(
                "spark.sql.extensions",
                "io.delta.sql.DeltaSparkSessionExtension",
            )
            .config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
            .config("delta.autoOptimize.optimizeWrite", "true")
            .config("delta.autoOptimize.autoCompact", "true")
            .config(
                "spark.delta.logStore.class",
                "org.apache.spark.sql.delta.storage.S3SingleDriverLogStore",
            )
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

        print("Spark session configured with Delta Lake and MinIO!")

    def process(self):
        # Define the path to the raw Delta table
        raw_delta_path = "s3a://lakehouse/delta/raw_iot_data"

        # Read changes from the raw Delta table using CDF
        cdf_stream = (
            self.spark.readStream.format("delta")
            .option("readChangeFeed", "true")
            .option("startingVersion", 0)
            .load(raw_delta_path)
        )

        # Path for the processed Delta table
        processed_delta_path = "s3a://lakehouse/delta/processed_iot_data"

        # Write changes to the processed Delta table
        processed_stream_query = (
            cdf_stream.writeStream.format("delta")
            .option("path", processed_delta_path)
            .option(
                "checkpointLocation",
                "s3a://lakehouse/delta/checkpoints/processed_iot_data",
            )
            .outputMode("append")
            .option("mergeSchema", "true")
            .start()
        )

        print("Propagating changes from raw_iot_data to processed_iot_data...")
        return processed_stream_query
