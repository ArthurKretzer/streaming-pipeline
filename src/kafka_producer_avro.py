import random
import time
from datetime import datetime, timezone

from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import StringSerializer

kafka_config = {
    "bootstrap.servers": "kafka-cpc.certi.org.br:31289",
    "client.id": "iot-sensor",
}

schema_registry_conf = {"url": "http://kafka-cpc.certi.org.br:32081"}

schema_registry_client = SchemaRegistryClient(schema_registry_conf)

with open("./src/temperature.json") as f:
    ride_schema_str = f.read()

temperature_avro_serializer = AvroSerializer(
    schema_registry_client, ride_schema_str
)

key_serializer = StringSerializer("utf_8")

producer_conf = {
    "bootstrap.servers": kafka_config["bootstrap.servers"],
    "key.serializer": key_serializer,
    "value.serializer": temperature_avro_serializer,
    "client.id": kafka_config["client.id"],
}

# Create SerializingProducer instance
producer = SerializingProducer(producer_conf)


def _delivery_report(err, msg):
    """Delivery callback confirmation."""
    if err is not None:
        print(f"Error in delivery: {err}")
    else:
        print(f"Mensagem entregue para {msg.topic()} [{msg.partition()}]")


def _produce_mocked_data():
    i = 0
    msg_count = 10000
    while i <= msg_count:
        # Creates random temperature data between 20.0
        # and 30.0 degrees Celsius.
        temperature = round(random.uniform(20.0, 30.0), 2)

        timestamp = int(
            datetime.now(timezone.utc).timestamp() * 1000
        )  # Convert to milliseconds
        message = {"source_timestamp": timestamp, "temperature": temperature}

        _send_message(key=timestamp, value=message)
        i += 1
        time.sleep(0.1)  # 10Hz


def _send_message(key, value):
    topic = "mocked-data"
    producer.produce(
        topic=topic,
        key=str(key),
        value=value,
        on_delivery=_delivery_report,
    )
    producer.poll(1)


if __name__ == "__main__":
    _produce_mocked_data()
