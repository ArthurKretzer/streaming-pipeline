FROM spark:3.5.4-python3

USER root

RUN apt-get update && apt-get install -y python3 python3-pip

USER spark

RUN mkdir -p /opt/spark/logs/events /opt/spark/metrics /opt/spark/conf

COPY ./config/spark-defaults.conf /opt/spark/conf/
COPY ./config/log4j2.properties /opt/spark/conf/

RUN /opt/spark/bin/spark-shell --packages \
    io.prometheus.jmx:jmx_prometheus_javaagent:1.0.1 \
    --verbose

RUN /opt/spark/bin/spark-shell --packages \
    org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,\
    io.delta:delta-spark_2.12:3.2.0,\
    org.apache.spark:spark-avro_2.12:3.5.1,\
    org.apache.hadoop:hadoop-aws:3.3.4,\
    com.amazonaws:aws-java-sdk-bundle:1.12.262,\
    org.apache.hadoop:hadoop-common:3.3.4,\
    org.apache.hadoop:hadoop-hdfs-client:3.3.4,\
    org.apache.hadoop:hadoop-auth:3.3.4,\
    org.apache.hadoop:hadoop-annotations:3.3.4,\
    com.github.luben:zstd-jni:1.4.5-4,\
    org.xerial.snappy:snappy-java:1.1.7.3,\
    org.apache.commons:commons-compress:1.20,\
    org.apache.hadoop:hadoop-client-api:3.3.4,\
    org.apache.hadoop:hadoop-client-runtime:3.3.4 --verbose

RUN cp -r /tmp/ivy2/jars/* /opt/spark/jars/

RUN rm -r /tmp/ivy2

EXPOSE 8080 18080