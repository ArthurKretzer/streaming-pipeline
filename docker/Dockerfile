FROM spark:3.5.4

USER root

RUN apt-get update && apt-get install -y python3 python3-pip

USER spark
RUN mkdir -p /opt/spark/jars /opt/spark/logs/events /opt/spark/metrics /opt/spark/conf

RUN curl -L -o /opt/spark/jars/jmx_prometheus_javaagent-1.0.1.jar https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/1.0.1/jmx_prometheus_javaagent-1.0.1.jar \
    && curl -L -o /opt/spark/jars/spark-sql-kafka-0-10_2.12-3.5.1.jar https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.1/spark-sql-kafka-0-10_2.12-3.5.1.jar \
    && curl -L -o /opt/spark/jars/delta-spark_2.12-3.2.0.jar https://repo1.maven.org/maven2/io/delta/delta-spark_2.12/3.2.0/delta-spark_2.12-3.2.0.jar \
    && curl -L -o /opt/spark/jars/spark-avro_2.12-3.5.1.jar https://repo1.maven.org/maven2/org/apache/spark/spark-avro_2.12/3.5.1/spark-avro_2.12-3.5.1.jar \
    && curl -L -o /opt/spark/jars/hadoop-aws-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
    && curl -L -o /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
    && curl -L -o /opt/spark/jars/hadoop-common-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-common/3.3.4/hadoop-common-3.3.4.jar \
    && curl -L -o /opt/spark/jars/hadoop-hdfs-client-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-hdfs-client/3.3.4/hadoop-hdfs-client-3.3.4.jar \
    && curl -L -o /opt/spark/jars/hadoop-auth-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-auth/3.3.4/hadoop-auth-3.3.4.jar \
    && curl -L -o /opt/spark/jars/hadoop-annotations-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-annotations/3.3.4/hadoop-annotations-3.3.4.jar \
    && curl -L -o /opt/spark/jars/zstd-jni-1.4.5-4.jar https://repo1.maven.org/maven2/com/github/luben/zstd-jni/1.4.5-4/zstd-jni-1.4.5-4.jar \
    && curl -L -o /opt/spark/jars/snappy-java-1.1.7.3.jar https://repo1.maven.org/maven2/org/xerial/snappy/snappy-java/1.1.7.3/snappy-java-1.1.7.3.jar \
    && curl -L -o /opt/spark/jars/commons-compress-1.20.jar https://repo1.maven.org/maven2/org/apache/commons/commons-compress/1.20/commons-compress-1.20.jar \
    && curl -L -o /opt/spark/jars/hadoop-client-api-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-client-api/3.3.4/hadoop-client-api-3.3.4.jar \
    && curl -L -o /opt/spark/jars/hadoop-client-runtime-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-client-runtime/3.3.4/hadoop-client-runtime-3.3.4.jar

COPY ./config/spark-defaults.conf /opt/spark/conf/
COPY ./config/log4j2.properties /opt/spark/conf/

EXPOSE 8080 18080