import pandas as pd


def calculate_latencies(df: pd.DataFrame) -> pd.DataFrame:
    df["source_kafka_latency"] = (
        df["timestamp"] - df["source_timestamp"]
    ).dt.total_seconds()
    df["kafka_landing_latency"] = (
        df["landing_timestamp"] - df["timestamp"]
    ).dt.total_seconds()

    return df
