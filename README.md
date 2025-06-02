# Edge-Cloud Streaming Pipeline Evaluation

This repository contains the implementation and experimental data for evaluating streaming pipelines across Edge and Cloud environments using Kafka, MinIO, Spark, and Delta Lake.

## Project Overview

This project aims to evaluate the performance and characteristics of streaming data pipelines deployed in both Edge and Cloud environments. The architecture leverages:

- Apache Kafka for stream processing
- MinIO for object storage
- Apache Spark for distributed computing
- Delta Lake for reliable data storage

## Repository Structure

```bash
.
├── data/ # Raw experimental data
├── docker/ # Docker configurations
├── kubernetes/ # K8s manifests and Helm charts
├── notebooks/ # Analysis notebooks
├── src/ # Source code
└── terraform/ # Infrastructure as Code
```

## Getting Started

### Prerequisites

- Docker
- Kubernetes
- Terraform
- `doctl` (DigitalOcean CLI)
- `kubectx`

### Setup and Deployment

You must have already created your kubernetes cluster on Digital Ocean and you must have your on-premises environment configured to excute the following commands.

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

### Available Commands

#### Infrastructure

- ``make start`` - Initialize Kubernetes context and deploy infrastructure
- ``make clean`` - Destroy infrastructure
- ``make services-external-ips`` - Display service endpoints and IPs

#### Data Pipeline

- ``make build-spark`` - Build Spark image
- ``make build-producer`` - Build producer image
- ``make build-consumer`` - Build consumer image
- ``make start-produce`` - Start all producers
- ``make start-consume`` - Start all consumers
- ``make stop-produce`` - Stop all producers
- ``make stop-consume`` - Stop all consumers

#### Experiments

The data/raw directory contains results from multiple experiments comparing Edge and Cloud deployments:

- First Experiment
- Second Experiment
- Third Experiment
- Fourth Experiment
- Experiment 05
- Experiment 06
