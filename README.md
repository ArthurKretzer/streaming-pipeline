# Edge-Cloud Streaming Pipeline Evaluation

This repository contains the implementation and experimental data for evaluating streaming pipelines across Edge and Cloud environments using Kafka, MinIO, Spark, and Delta Lake. The project simulates a scenario where robots send telemetry data (control power, accelerometer, gyro) to a central data lakehouse.

## Project Overview

This project aims to evaluate the performance and characteristics of streaming data pipelines deployed in both Edge and Cloud environments. The architecture leverages:

- **Apache Kafka**: For reliable stream processing and buffering.
- **MinIO**: For S3-compatible object storage.
- **Apache Spark**: For distributed stream processing and ETL.
- **Delta Lake**: For reliable, ACID-compliant data storage on top of the data lake.

The system simulates robots generating data at a frequency of 10Hz. The data is ingested into Kafka, processed by Spark Structured Streaming, and stored in Delta Lake tables in MinIO.

## Repository Structure

```bash
.
├── data/           # Raw experimental data and datasets
├── docker/         # Dockerfiles for Spark, Producer, and Consumer
├── kubernetes/     # Kubernetes manifests and Helm charts for deployment
├── notebooks/      # Jupyter notebooks for data analysis and visualization
├── src/            # Source code for Producers, Consumers, and Utilities
│   ├── common/     # Shared utility code
│   ├── deploy/     # Deployment scripts
│   ├── schemas/    # Avro schemas for data serialization
│   ├── main.py     # Entry point for the application
│   └── ...
├── terraform/      # Terraform scripts for infrastructure provisioning
├── Makefile        # Automation commands for build and deployment
└── README.md       # Project documentation
```

## Getting Started

### Prerequisites

- Docker
- Kubernetes
- Terraform
- `doctl` (DigitalOcean CLI)
- `kubectx`
- Python 3.10+

### Setup and Deployment

You must have already created your kubernetes cluster on Digital Ocean and you must have your on-premises environment configured to execute the following commands.

For setting up the infrastructure, the code is included as submodules:

- **Edge Environment**: `terraform/edge-deploy`
- **Cloud Environment**: `terraform/cloud-deploy`

Ensure you initialize the submodules:

```bash
git submodule update --init --recursive
```

Please refer to the documentation within those directories to set up your Kubernetes clusters if needed.

1. Initialize the infrastructure:

    ```bash
    make start
    ```

2. Build and deploy producers:

    ```bash
    make start-produce
    ```

3. Deploy consumers:

    ```bash
    make start-consume
    ```

### Running Experiments

You can run experiments with different numbers of simulated robots to test the scalability of the pipeline. The available commands allow you to simulate 1, 10, 50, or 100 robots concurrently.

#### Standard Production (1 Robot)

```bash
# Cloud only
make produce-control-power-cloud
# Edge only
make produce-control-power-edge
# Both
make start-produce
```

#### Scalability Experiments

To run experiments with a specific number of robots:

- **10 Robots**:

    ```bash
    # Cloud only
    make produce-10-robots-cloud
    # Edge only
    make produce-10-robots-edge
    # Both
    make produce-10-robots
    ```

- **50 Robots**:

    ```bash
    # Cloud only
    make produce-50-robots-cloud
    # Edge only
    make produce-50-robots-edge
    # Both
    make produce-50-robots
    ```

- **100 Robots**:

    ```bash
    # Cloud only
    make produce-100-robots-cloud
    # Edge only
    make produce-100-robots-edge
    # Both
    make produce-100-robots
    ```

### Available Commands

#### Infrastructure

- `make start` - Initialize Kubernetes context and deploy infrastructure
- `make clean` - Destroy infrastructure
- `make services-external-ips` - Display service endpoints and IPs

#### Data Pipeline

- `make build-spark` - Build Spark image
- `make build-producer` - Build producer image
- `make build-consumer` - Build consumer image
- `make start-produce` - Start all producers (1 robot default)
- `make start-consume` - Start all consumers
- `make stop-produce` - Stop all producers
- `make stop-produce` - Stop all producers
- `make stop-consume` - Stop all consumers
- `make collect-metrics` - Collect Prometheus metrics (requires EDGE_IP, CLOUD_IP, EXP_NAME)

## Data Collection

### Prometheus Metrics

To collect Prometheus metrics from both Edge and Cloud environments after an experiment, use the `collect-metrics` target. You need to provide the IPs of the Edge and Cloud nodes, and an experiment name.

```bash
make collect-metrics EDGE_IP=<edge_ip> CLOUD_IP=<cloud_ip> EXP_NAME=<experiment_name>
```

The metrics will be saved in `data/raw/execution_metrics/<experiment_name>`.

### Spark Event Logs

Spark event logs must be collected manually from the Spark History Server or the Spark UI.

1. Access the Spark UI/History Server.
2. Download the event logs for your application.
3. Save the file as `eventLogs.json` in `data/raw/<experiment_name>/`.

After saving the logs, you can use the `data/eventlog_analysis.py` script to parse and analyze them. Ensure you update the `experiment_name` variable in the script or modify it to accept arguments as needed.

## Citation

If you use this work in your research, please cite it as follows:

```bibtex
@misc{streaming_pipeline_evaluation,
  author = {Arthur Raulino Kretzer},
  title = {Edge-Cloud Streaming Pipeline Evaluation},
  year = {2024},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/arthurkretzer/streaming-pipeline}}
}
```
