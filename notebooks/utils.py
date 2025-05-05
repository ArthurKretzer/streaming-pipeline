import re

import pandas as pd


def fix_timestamps_timezone(df: pd.DataFrame) -> pd.DataFrame:
    # Corrigindo 'source_timestamp' que está como São Paulo mas deveria ser UTC
    df["source_timestamp"] = (
        df["source_timestamp"]
        .dt.tz_convert(None)  # Remove o timezone mantendo o horário
        .dt.tz_localize("UTC")  # Aplica UTC como se o horário fosse UTC mesmo
    )
    # Adiciona 3 horas e seta fuso como UTC
    df["source_timestamp"] = df["source_timestamp"] - pd.Timedelta(hours=3)
    df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
    df["landing_timestamp"] = df["landing_timestamp"].dt.tz_convert("UTC")

    return df


def time_filter(
    df: pd.DataFrame, start_time: pd.Timestamp, end_time: pd.Timestamp
) -> pd.DataFrame:
    # Make sure the 'timestamp' column is in datetime format
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Convert from UTC to GMT-3 (America/Sao_Paulo is actually GMT-3)
    df["timestamp"] = df["timestamp"].dt.tz_convert("America/Sao_Paulo")

    df = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)]
    return df


def simplify_pod_name(pod_name: str) -> str:
    # 1. Remove common hash suffixes (e.g., -6b6bf85947-b67tc or -74c4cb664h8mx)
    pod_name = re.sub(r"-[a-z0-9]{5,}(?=$|-)", "", pod_name)

    # 2. Remove deployment hashes (common in statefulsets/deployments)
    pod_name = re.sub(r"-[a-z0-9]{8,}$", "", pod_name)

    # 3. Replace very long names with initials or shorter known aliases
    known_aliases = {
        "kube-prometheus-stack-prometheus-node-exporter": "node-exporter",
        "kube-prometheus-stack-kube-state-metrics": "state-metrics",
        "airbyte-default-connector-builder-server": "airbyte-builder",
        "airbyte-default-server": "airbyte-server",
        "airbyte-default-worker": "airbyte-worker",
        "airbyte-default-workload-launcher": "airbyte-launcher",
        "labfaber-kafka-schema-registry-cp-schema-registry": "kafka-schema-registry",
        "labfaber-kafka-exporter": "kafka-exporter",
        "labfaber-kafka-ui": "kafka-ui",
        "labfaber-zookeeper": "zk",
        "labfaber-kafka": "kafka",
        "longhorn-driver-deployer": "longhorn-deployer",
        "longhorn-csi-plugin": "longhorn-csi",
        "longhorn-manager": "longhorn-mgr",
        "open-metadata-deps-db-migrations": "om-db-migrations",
        "open-metadata-deps-scheduler": "om-scheduler",
        "open-metadata-deps-triggerer": "om-triggerer",
        "open-metadata-deps-web": "om-web",
        "openmetadata": "openmetadata",
        "spark-operator-controller": "spark-ctrl",
        "spark-operator-webhook": "spark-hook",
        "deltalakewithminio": "dl-minio",
        "streaming-pipeline-kafka-avro-to-delta-driver": "spark-driver",
        "deploy-spark-history-server": "spark-history",
    }
    for long, short in known_aliases.items():
        if pod_name.startswith(long):
            return pod_name.replace(long, short)

    # 4. Trim overly verbose prefixes but keep the key identity
    parts = pod_name.split("-")
    if len(parts) > 3:
        return "-".join(parts[:3])  # e.g., 'argocd-server-abc123' → 'argocd-server-abc'

    return pod_name


def get_selected_pods(df: pd.DataFrame) -> str:
    # List of name patterns (stable prefixes)
    pod_patterns = [
        "minio-community",
        "labfaber-cruise-control",
        "labfaber-kafka",
        "labfaber-kafka-schema-registry",
        "labfaber-kafka-ui",
        "labfaber-zookeeper",
        "strimzi-cluster-operator",
        "deltalakewithminio",
        "deploy-spark-history-server",
        "streaming-pipeline-kafka-avro-to-delta-driver",
        "spark-operator-controller",
        "spark-operator-webhook",
    ]

    # List of all pods (as a Python list)
    all_pods = df["pod"].unique()

    # Select pods that match any pattern
    selected_pods = [
        pod for pod in all_pods if any(pod.startswith(p) for p in pod_patterns)
    ]

    return selected_pods


def get_true_spark_run_starts(df_status: pd.DataFrame):
    """
    Extracts Spark driver/executor start times by identifying the first Running phase
    that is not followed by a terminal phase (Pending, Failed, Succeeded, etc.)
    """
    spark_df = df_status[
        (df_status["pod"].str.contains("driver|exec", case=False))
        & (df_status["value"] == 1.0)
    ].sort_values(["timestamp", "pod"])

    valid_starts = []

    for pod, pod_df in spark_df.groupby("pod"):
        phases = pod_df[["timestamp", "phase"]].values
        for i, (ts, phase) in enumerate(phases):
            if phase != "Running":
                continue
            # Check if there's any non-running *after* this point
            future_phases = [p for _, p in phases[i + 1 :]]
            if all(p == "Running" for p in future_phases):
                # Running never ends
                valid_starts.append((pod, ts))
                break
            if any(
                p in ["Failed", "Succeeded", "Pending", "Unknown"]
                for p in future_phases
            ):
                # This is a real start that will transition
                valid_starts.append((pod, ts))
                break

    return pd.DataFrame(valid_starts, columns=["pod", "timestamp"])
