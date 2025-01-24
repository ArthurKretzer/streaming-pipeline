# Pyspark build
FROM python:3.13-slim AS pyspark-base

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Java (required for PySpark)
RUN apt-get update && apt-get install -y openjdk-17-jdk-headless && apt-get clean

# Set environment variables for Java and Spark
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV SPARK_VERSION=3.5.4
ENV HADOOP_VERSION=3
ENV SPARK_HOME=/opt/spark
ENV PATH=$SPARK_HOME/bin:$PATH

RUN curl -L https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz \
    | tar -xz -C /opt/ && mv /opt/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} /opt/spark

RUN pip install --upgrade pip && \
    pip install --no-cache-dir pyspark==${SPARK_VERSION}

## App build
FROM pyspark-base AS app-build
COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /uvx /bin/

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

WORKDIR /app

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
ADD ./src /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Place entry points in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

CMD ["fastapi", "run", "--host", "0.0.0.0", "/app/data_backend/app.py", "--port", "8080"]