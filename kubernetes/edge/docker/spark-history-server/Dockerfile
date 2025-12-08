FROM spark:3.5.4
WORKDIR /

USER root

RUN apt-get update && apt-get install -y \
    && mkdir -p /opt/spark/logs/ /opt/spark/logs/events /opt/spark/metrics \
    && chown -R spark:spark /opt/spark/logs/ /opt/spark/logs/events /opt/spark/metrics

USER spark

# add new entrypoint
ENTRYPOINT ["bash", "/opt/spark/bin/spark-class", "org.apache.spark.deploy.history.HistoryServer"]
