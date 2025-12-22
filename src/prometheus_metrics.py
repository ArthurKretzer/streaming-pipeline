import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from prometheus_api_client import MetricRangeDataFrame, PrometheusConnect


def collect_metrics(prometheus_uri: str, experiment_name: str):
    print("Starting metrics collection...")
    PROMETHEUS_URL = prometheus_uri
    METRICS = [
        "minio_cluster_usage_total_bytes",
        "minio_node_io_read_bytes",
        "minio_node_io_write_bytes",
        "minio_node_drive_io_waiting",
        "minio_node_drive_online_total",
        "minio_node_drive_total_bytes",
        "minio_node_drive_used_bytes",
        "minio_node_drive_errors_timeout",
        "minio_node_drive_errors_availability",
        "minio_s3_requests_incoming_total",
        "minio_s3_requests_waiting_total",
        "minio_s3_requests_total",
        "minio_s3_requests_errors_total",
        "minio_s3_traffic_received_bytes",
        "minio_s3_traffic_sent_bytes",
        "minio_node_process_cpu_total_seconds",
        "minio_node_drive_latency_us",
        "minio_node_process_resident_memory_bytes",
        "minio_process_cpu_seconds_total",
        "minio_process_virtual_memory_bytes",
        "minio_process_virtual_memory_max_bytes",
        "kafka_server_brokertopicmetrics_messagesin_total",
        "kafka_server_brokertopicmetrics_bytesin_total",
        "kafka_server_brokertopicmetrics_bytesout_total",
        "kafka_network_requestmetrics_requests_total",
        "kafka_server_replicafetchermanager_maxlag",
        "kafka_server_replicamanager_underreplicatedpartitions",
        "kafka_server_replicamanager_offlinereplicacount",
        "kafka_server_socket_server_metrics_io_ratio",
        "kafka_server_socket_server_metrics_iotime",
        "kafka_topic_partitions",
        "kafka_topic_partition_replicas",
        "kafka_topic_partition_in_sync_replica",
        "kafka_topic_partition_current_offset",
        "kafka_network_requestmetrics_errors_total",
        "kafka_network_requestmetrics_requests_total",
        "kafka_network_requestmetrics_responsequeuetimems",
        "kafka_consumer_io_ratio",
        "kafka_consumer_io_wait_time_ns_avg",
        "kafka_consumer_node_request_latency_avg",
        "kafka_consumer_node_request_size_avg",
        "kafka_consumer_outgoing_byte",
        "kafka_consumer_connection_count",
        "jvm_memory_bytes_used",
        "jvm_memory_used_bytes",
        "container_cpu_usage_seconds_total",
        "container_fs_reads_bytes_total",
        "container_fs_writes_bytes_total",
        "container_memory_usage_bytes",
        "kube_pod_status_phase",
        "spark_application_count",
        "spark_application_running_count",
        "spark_application_start_latency_seconds_count",
        "spark_application_start_latency_seconds_histogram_bucket",
        "spark_application_start_latency_seconds_histogram_count",
        "spark_application_start_latency_seconds_histogram_sum",
        "spark_application_start_latency_seconds_sum",
        "spark_application_submit_count",
        "spark_application_success_count",
        "spark_application_success_execution_time_seconds_count",
        "spark_application_success_execution_time_seconds_sum",
        "spark_executor_failure_count",
        "spark_executor_running_count",
        "spark_executor_success_count",
        # Spark Driver Metrics (Prometheus Servlet)
        "metrics_jvm_memory_heap_used",
        "metrics_jvm_memory_heap_committed",
        "metrics_jvm_threads_count",
        "metrics_spark_driver_dagScheduler_job_activeJobs",
        "metrics_spark_driver_dagScheduler_stage_activeStages",
        "metrics_spark_driver_dagScheduler_stage_failedStages",
        "metrics_spark_driver_BlockManager_memory_memUsed_MB",
        # Spark Structured Streaming Metrics
        "metrics_spark_sql_streaming_inputRate",
        "metrics_spark_sql_streaming_processingRate",
        "metrics_spark_sql_streaming_latency",
        "metrics_spark_sql_streaming_states_rowsTotal",
        "metrics_spark_sql_streaming_states_usedBytes",
        "metrics_spark_sql_streaming_lastProgress_numInputRows",
        "metrics_spark_sql_streaming_lastProgress_processedRowsPerSecond",
    ]

    project_root = Path.cwd()

    SAVE_DIR = f"{project_root}/data/raw/execution_metrics/{experiment_name}"

    print(f"Creating dir for experiment {experiment_name}")
    os.makedirs(SAVE_DIR, exist_ok=True)

    print("Connecting to Prometheus...")
    prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=False)

    print("Collecting metrics...")
    # Intervalo de tempo: última hora
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=4, minutes=00)

    collected_dfs = {}
    for metric in METRICS:
        print(f"Collecting metric {metric}")
        try:
            data = prom.get_metric_range_data(
                metric_name=metric,
                start_time=start_time,
                end_time=end_time,
                chunk_size=timedelta(minutes=10),
            )
            if data:
                df = MetricRangeDataFrame(data)
                if not df.empty:
                    filename = os.path.join(SAVE_DIR, f"{metric}.parquet")
                    table = pa.Table.from_pandas(df)
                    pq.write_table(table, filename)
                    print(f"Saved: {filename}")
                    collected_dfs[metric] = df
        except Exception as e:
            print(f"Error collecting metrics {metric}: {e}")

    print(f"Collected metrics: {list(collected_dfs.keys())}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Collect Prometheus metrics.")
    parser.add_argument(
        "--edge-ip", required=False, help="IP address of the Edge node"
    )
    parser.add_argument(
        "--cloud-ip", required=False, help="IP address of the Cloud node"
    )
    parser.add_argument(
        "--experiment-name", required=True, help="Name of the experiment"
    )

    args = parser.parse_args()

    if args.edge_ip:
        collect_metrics(
            f"http://{args.edge_ip}:30090", f"{args.experiment_name}_edge"
        )

    if args.cloud_ip:
        collect_metrics(
            f"http://{args.cloud_ip}:30090", f"{args.experiment_name}_cloud"
        )
