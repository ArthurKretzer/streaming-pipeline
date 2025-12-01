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
make produce-control-power-cloud
# or
make produce-control-power-edge
```

#### Scalability Experiments

To run experiments with a specific number of robots on the cloud environment:

- **10 Robots**:

    ```bash
    make produce-10-robots-cloud
    ```

- **50 Robots**:

    ```bash
    make produce-50-robots-cloud
    ```

- **100 Robots**:

    ```bash
    make produce-100-robots-cloud
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
- `make stop-consume` - Stop all consumers

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
