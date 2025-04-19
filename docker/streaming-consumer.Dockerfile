FROM arthurkretzer/spark:3.5.4

USER root

#Confluent kafka libraries
RUN apt-get update && \
    apt-get install -y \
    python3-dev \
    gcc \
    libssl-dev \
    libffi-dev \
    librdkafka-dev \
    python3-pip && \
    pip install --upgrade pip

ENV WORK_DIR=/app

# Install dependencies as root
RUN pip install pyspark>=3.5.4 sparkmeasure>=0.24.0 confluent-kafka[avro,schemaregistry]>=2.8.0

# Create directories
RUN mkdir -p ${WORK_DIR}
WORKDIR ${WORK_DIR}

# Copy project files
COPY . /app

# Fix permissions after installation
RUN chown -R spark:spark ${WORK_DIR}

# Switch to spark user at the end
USER spark
