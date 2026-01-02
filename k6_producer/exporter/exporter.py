import pandas as pd
from influxdb_client import InfluxDBClient
import argparse
import sys
import os


def export_to_parquet(url, token, org, bucket, output_dir, start_time, stop_time):
    print(f"Connecting to InfluxDB at {url}, Org: {org}, Bucket: {bucket}...")

    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        # Check connection implicitly by listing buckets or similar?
        # But setup is lazy, query will fail if connection is bad.
    except Exception as e:
        print(f"Error creating InfluxDB client: {e}")
        sys.exit(1)

    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")
        except OSError as e:
            print(f"Error creating directory {output_dir}: {e}")
            sys.exit(1)

    print(f"Querying measurements from bucket '{bucket}'...")

    # In Flux, to get list of measurements:
    # import "influxdata/influxdb/schema"
    # schema.measurements(bucket: "k6")

    query_measurements = f'''
    import "influxdata/influxdb/schema"
    schema.measurements(bucket: "{bucket}")
    '''

    try:
        query_api = client.query_api()
        result_measurements = query_api.query(query_measurements)
    except Exception as e:
        print(f"Error querying measurements: {e}")
        sys.exit(1)

    measurements = []
    for table in result_measurements:
        for record in table.records:
            measurements.append(record.get_value())

    if not measurements:
        print("No measurements found.")
        return

    print(f"Found {len(measurements)} measurements.")

    count = 0
    for m_name in measurements:
        print(f"Processing measurement: {m_name}")

        # Flux query to get all data for measurement
        # Note: Depending on data size, this might be heavy.
        # k6 V1 output stores fields in the measurement.
        query_data = f'''
        from(bucket: "{bucket}")
          |> range(start: {start_time}, stop: {stop_time})
          |> filter(fn: (r) => r["_measurement"] == "{m_name}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        try:
            # query_data_frame returns a generator or dataframe?
            # client.query_api().query_data_frame works nicely
            df = query_api.query_data_frame(query_data)

            if df.empty:
                print(f"No data for measurement: {m_name}")
                continue

            # Clean up default Flux columns if desired, e.g. result, table, _start, _stop, _measurement
            # But users might want them. Let's keep them or just strip common ones.
            # k6 schema: typically contains tags + fields + time.

            # Clean filename
            safe_name = "".join(
                [c if c.isalnum() or c in ("-", "_") else "_" for c in m_name]
            )
            output_file = os.path.join(output_dir, f"{safe_name}.parquet")

            print(f"Saving to {output_file}...")
            df.to_parquet(output_file, index=False)
            count += 1

        except Exception as e:
            print(f"Error querying/saving data for {m_name}: {e}")

    if count == 0:
        print("No parquet files were created.")
    else:
        print(f"Successfully created {count} parquet files in {output_dir}")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export InfluxDB 2.0 data to Parquet files per measurement"
    )
    parser.add_argument("--url", default="http://localhost:8086", help="InfluxDB URL")
    parser.add_argument(
        "--token", default="my-super-secret-auth-token", help="InfluxDB Token"
    )
    parser.add_argument("--org", default="my-org", help="InfluxDB Org")
    parser.add_argument("--bucket", default="k6", help="InfluxDB Bucket")
    parser.add_argument(
        "--output-dir", default="../data/raw/k6_metrics", help="Output directory path"
    )
    parser.add_argument(
        "--start", default="0", help="Start time (UTC ISO 8601 or relative)"
    )
    parser.add_argument(
        "--stop", default="now()", help="Stop time (UTC ISO 8601 or relative)"
    )

    args = parser.parse_args()

    export_to_parquet(
        args.url,
        args.token,
        args.org,
        args.bucket,
        args.output_dir,
        args.start,
        args.stop,
    )
