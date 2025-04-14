import io
import time

from minio import Minio
from minio.error import S3Error

# MinIO Configuration
MINIO_ENDPOINT = "localhost:9000"  # Example: "localhost:9000"
ACCESS_KEY = "ark"
SECRET_KEY = "123456789"
BUCKET_NAME = "sandbox"
OBJECT_NAME = "test-object.txt"
TEST_DATA = b"Hello, this is a latency test!"  # Small sample data

# Initialize MinIO Client
client = Minio(
    MINIO_ENDPOINT,
    access_key=ACCESS_KEY,
    secret_key=SECRET_KEY,
    secure=False,  # Change to True if using HTTPS
)

# Ensure bucket exists
try:
    if not client.bucket_exists(BUCKET_NAME):
        client.make_bucket(BUCKET_NAME)
        print(f"Bucket '{BUCKET_NAME}' created.")
except S3Error as err:
    print(f"Bucket error: {err}")

# Measure PUT latency
try:
    start_time = time.time()
    client.put_object(
        BUCKET_NAME, OBJECT_NAME, io.BytesIO(TEST_DATA), len(TEST_DATA)
    )
    put_latency = time.time() - start_time
    print(f"PUT Latency: {put_latency:.6f} seconds")
except S3Error as err:
    print(f"PUT Error: {err}")

# Measure GET latency
try:
    start_time = time.time()
    response = client.get_object(BUCKET_NAME, OBJECT_NAME)
    data = response.read()  # Read response to measure total latency
    response.close()
    response.release_conn()
    get_latency = time.time() - start_time
    print(f"GET Latency: {get_latency:.6f} seconds")
except S3Error as err:
    print(f"GET Error: {err}")
