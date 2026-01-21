import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# --- Configuration ---
START_TIME_EDGE_STR = "2026-01-05 16:07:20"
END_TIME_EDGE_STR = "2026-01-05 16:25:00"
START_TIME_CLOUD_STR = "2026-01-05 13:31:00"
END_TIME_CLOUD_STR = "2026-01-05 13:48:10"

# Timezone offset: User provided GMT-3, Prometheus is UTC. Add 3h.
TIMEZONE_OFFSET = pd.Timedelta(hours=3)

EDGE_PATH = "../../data/raw/final-01/final-01_edge/kube_pod_status_phase.parquet"
CLOUD_PATH = "../../data/raw/final-01/final-01_cloud/kube_pod_status_phase.parquet"

NAMESPACES_OF_INTEREST = ["ingestion", "spark-jobs", "deepstorage"]

OUTPUT_FILE = "pod_disruption_chart.png"

# --- Helper Functions ---


def load_and_filter_data(filepath, start_time, end_time, namespaces):
    """Loads parquet data and filters by time and namespace."""
    if not os.path.exists(filepath):
        print(f"Error: File not found at {filepath}")
        return None

    df = pd.read_parquet(filepath)

    # Filter by time
    df = df[(df.index >= start_time) & (df.index <= end_time)]

    # Filter by namespace
    df = df[df["namespace"].isin(namespaces)]

    # Filter for Running state
    # We are interested in when the pod is 'Running' (value=1)
    df = df[(df["phase"] == "Running") & (df["value"] == 1.0)]

    return df


def get_pod_intervals(df, start_time_ref):
    """
    Converts time series data into intervals (start, duration) for each pod.
    Returns a list of dicts: {'pod': pod_name, 'start_offset': seconds, 'duration': seconds}
    """
    intervals = []

    # Group by pod
    for pod_name, group in df.groupby("pod"):
        # Sort by time
        group = group.sort_index()

        if group.empty:
            continue

        # We need to detect continuous running blocks.
        # Since we only have 'Running' samples, we can try to group them if they are close.
        # However, a simpler approach for visualization is to assume that if we have a sample,
        # it was running at that time.
        # To make a Gantt chart, we ideally need start and end of running phases.
        # Given the scrape interval (likely 30s based on previous data inspection),
        # we can assume continuity if gaps are small.

        # Calculate time diffs
        times = group.index
        diffs = times.to_series().diff().dt.total_seconds()

        # Identify breaks (e.g., > 60 seconds gap means it probably stopped/restarted or was scraping missing)
        # Using 45s as threshold for 30s scrape interval
        break_threshold = 45.0

        current_start = times[0]
        prev_time = times[0]

        for i in range(1, len(times)):
            time = times[i]
            if diffs.iloc[i] > break_threshold:
                # Gap detected, close previous interval
                duration = (prev_time - current_start).total_seconds()
                # Ensure a minimum visibility width (e.g. 5s) for single points
                if duration < 5:
                    duration = 30

                intervals.append(
                    {
                        "pod": pod_name,
                        "start_offset": (
                            current_start - start_time_ref
                        ).total_seconds(),
                        "duration": duration,
                        "namespace": group["namespace"].iloc[
                            0
                        ],  # Assume namespace doesn't change
                    }
                )
                current_start = time

            prev_time = time

        # Add the last interval
        duration = (prev_time - current_start).total_seconds()
        if duration < 5:
            duration = 30

        intervals.append(
            {
                "pod": pod_name,
                "start_offset": (current_start - start_time_ref).total_seconds(),
                "duration": duration,
                "namespace": group["namespace"].iloc[0],
            }
        )

    return pd.DataFrame(intervals)


def detect_prometheus_gaps(df, start_time_ref, threshold=45.0):
    """
    Detects gaps in Prometheus scrapes within the dataframe.
    Returns list of dicts: {'start_offset': s, 'duration': s}
    """
    if df.empty:
        return []

    timestamps = pd.Series(df.index.unique()).sort_values()
    diffs = timestamps.diff().dt.total_seconds()

    gaps = []
    gap_indices = diffs[diffs > threshold].index

    for idx in gap_indices:
        t_end = timestamps[idx]
        t_start = timestamps[idx - 1]

        gaps.append(
            {
                "start_offset": (t_start - start_time_ref).total_seconds(),
                "end_offset": (t_end - start_time_ref).total_seconds(),
                "duration": (t_end - t_start).total_seconds(),
            }
        )

    return gaps


def plot_gantt(ax, df_intervals, title, x_limit, color_map, gaps=[]):
    """Plots a Gantt chart on the given axes."""

    # Plot gaps first (background)
    for gap in gaps:
        ax.axvspan(
            gap["start_offset"],
            gap["end_offset"],
            color="gray",
            alpha=0.3,
            label="Metric Gap"
            if "Metric Gap" not in ax.get_legend_handles_labels()[1]
            else "",
        )
    if df_intervals.empty:
        ax.text(0.5, 0.5, "No Running Pods Found", transform=ax.transAxes, ha="center")
        ax.set_xlim(0, x_limit)
        return

    # Sort pods to group by namespace for better visuals
    df_intervals = df_intervals.sort_values(by=["namespace", "pod"])

    # Map pod names to y-positions
    unique_pods = df_intervals["pod"].unique()
    y_pos = np.arange(len(unique_pods))
    pod_to_y = dict(zip(unique_pods, y_pos))

    # Plot bars
    for i, row in df_intervals.iterrows():
        ax.barh(
            y=pod_to_y[row["pod"]],
            width=row["duration"],
            left=row["start_offset"],
            height=0.6,
            color=color_map.get(
                row["namespace"], "black"
            ),  # Fallback to black if missing
            edgecolor="none",
            alpha=0.9,
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(unique_pods, fontsize=12)
    ax.tick_params(axis="x", labelsize=12)
    ax.set_ylim(-0.5, len(unique_pods) - 0.5)
    ax.set_xlim(0, x_limit)
    ax.set_xlabel("Elapsed Time (s)", fontsize=12)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(True, axis="x", linestyle="--", alpha=0.5)

    # Add legend
    # Only include namespaces present in this subplot
    unique_namespaces = df_intervals["namespace"].unique()
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=color_map[ns])
        for ns in unique_namespaces
        if ns in color_map
    ]
    labels = [ns for ns in unique_namespaces if ns in color_map]

    if gaps:
        handles.append(plt.Rectangle((0, 0), 1, 1, color="gray", alpha=0.3))
        labels.append("Metric Gap")

    ax.legend(handles, labels, loc="upper right", fontsize="small")


import re


def simplify_pod_name(pod_name: str) -> str:
    # 1. Handle Spark Executors (preserve number)
    # Pattern: ...-exec-<number>
    match = re.search(r"-exec-(\d+)$", pod_name)
    if match:
        return f"spark-executor-{match.group(1)}"

    # 2. Known aliases
    known_aliases = {
        "alertmanager-monitoring-alertmanager-0": "prometheus-alerts",
        "argocd-application-controller-1": "argocd-controller-1",
        "argocd-application-controller-0": "argocd-controller-0",
        "argocd-notifications-controller": "argocd-notifications-controller",
        "argocd-applicationset-controller": "argocd-controller",
        "argocd-redis": "argocd-redis",
        "argocd-repo-server": "argocd-repo-server",
        "argocd-server": "argocd-server",
        "ntp-configurator": "ntp-sync",
        "coredns": "coredns",
        "svclb-traefik": "traefik",
        "traefik": "traefik",
        "local-path-provisioner": "local-path-provisioner",
        "metrics-server": "metrics-server",
        "minio-community": "minio",
        "monitoring-operator": "monitoring-operator",
        "prometheus-monitoring-prometheus-0": "prometheus",
        "kube-prometheus-stack-prometheus-node-exporter": "prometheus",
        "kube-prometheus-stack-kube-state-metrics": "prometheus",
        "streaming-cruise-control": "kafka-cruise-control",
        "master-cruise-control": "kafka-cruise-control",
        "argocd-dex-server": "argocd-dex-server",
        "kube-prometheus-stack-grafana-0": "grafana",
        "streaming-kafka-2": "kafka-broker-2",
        "streaming-kafka-0": "kafka-broker-0",
        "streaming-kafka-1": "kafka-broker-1",
        "streaming-kafka-3": "kafka-broker-3",
        "master-kafka-2": "kafka-broker-2",
        "master-kafka-0": "kafka-broker-0",
        "master-kafka-1": "kafka-broker-1",
        "master-kafka-3": "kafka-broker-3",
        "streaming-kafka-schema-registry-cp-schema-registry": "schema-registry",
        "kafka-schema-registry-cp-schema-registry": "schema-registry",
        "streaming-kafka-exporter": "kafka-exporter",
        "master-kafka-exporter": "kafka-exporter",
        "streaming-kafka-ui": "kafka-ui",
        "strimzi-cluster-operator": "strimzi-operator",
        "spark-operator-controller": "spark-operator",
        "spark-operator-webhook": "spark-hook",
        "spark-executor": "spark-executor",
        "deltalakewithminio": "spark-executor",
        "streaming-pipeline-kafka-avro-to-delta-driver": "spark-driver",
        "streaming-zookeeper-1": "zookeeper-1",
        "streaming-zookeeper-2": "zookeeper-2",
        "streaming-zookeeper-3": "zookeeper-3",
        "streaming-zookeeper-0": "zookeeper-0",
        "master-zookeeper-1": "zookeeper-1",
        "master-zookeeper-2": "zookeeper-2",
        "master-zookeeper-3": "zookeeper-3",
        "master-zookeeper-0": "zookeeper-0",
        "cilium": "do-resources",
        "cpc-bridge-proxy": "do-resources",
        "csi-do-node": "do-resources",
        "do-node-agent": "do-resources",
        "konnectivity-agent": "do-resources",
        "hubble-relay": "do-resources",
        "hubble-ui": "do-resources",
    }
    for long, short in known_aliases.items():
        if pod_name.startswith(long):
            return short

    return pod_name


# --- Main Execution ---


def main():
    # Parse times and apply offset to match UTC data
    start_edge = pd.to_datetime(START_TIME_EDGE_STR) + TIMEZONE_OFFSET
    end_edge = pd.to_datetime(END_TIME_EDGE_STR) + TIMEZONE_OFFSET
    start_cloud = pd.to_datetime(START_TIME_CLOUD_STR) + TIMEZONE_OFFSET
    end_cloud = pd.to_datetime(END_TIME_CLOUD_STR) + TIMEZONE_OFFSET

    # Calculate global max duration to align X-axis scales
    duration_edge = (end_edge - start_edge).total_seconds()
    duration_cloud = (end_cloud - start_cloud).total_seconds()
    max_duration = max(duration_edge, duration_cloud)

    print("Loading Cloud Data...")
    df_cloud = load_and_filter_data(
        CLOUD_PATH, start_cloud, end_cloud, NAMESPACES_OF_INTEREST
    )
    intervals_cloud = get_pod_intervals(df_cloud, start_cloud)

    # Reload raw cloud data to check gaps (before pod filtering)
    df_cloud_raw = pd.read_parquet(CLOUD_PATH)
    # Filter only by time for gap check
    df_cloud_raw = df_cloud_raw[
        (df_cloud_raw.index >= start_cloud) & (df_cloud_raw.index <= end_cloud)
    ]
    gaps_cloud = detect_prometheus_gaps(df_cloud_raw, start_cloud)
    if gaps_cloud:
        print(f"Found {len(gaps_cloud)} gaps in Cloud metrics.")

    if not intervals_cloud.empty:
        intervals_cloud["pod"] = intervals_cloud["pod"].apply(simplify_pod_name)
        # Filter for interested pods
        allowed_prefixes = [
            "kafka-broker",
            "zookeeper",
            "spark-driver",
            "spark-executor",
            "minio",
        ]
        intervals_cloud = intervals_cloud[
            intervals_cloud["pod"].str.startswith(tuple(allowed_prefixes))
        ]

    print(f"Found {len(intervals_cloud)} intervals for Cloud.")

    print("Loading Edge Data...")
    df_edge = load_and_filter_data(
        EDGE_PATH, start_edge, end_edge, NAMESPACES_OF_INTEREST
    )
    intervals_edge = get_pod_intervals(df_edge, start_edge)

    # Reload raw edge data to check gaps
    df_edge_raw = pd.read_parquet(EDGE_PATH)
    df_edge_raw = df_edge_raw[
        (df_edge_raw.index >= start_edge) & (df_edge_raw.index <= end_edge)
    ]
    gaps_edge = detect_prometheus_gaps(df_edge_raw, start_edge)
    if gaps_edge:
        print(f"Found {len(gaps_edge)} gaps in Edge metrics.")

    if not intervals_edge.empty:
        intervals_edge["pod"] = intervals_edge["pod"].apply(simplify_pod_name)
        allowed_prefixes = [
            "kafka-broker",
            "zookeeper",
            "spark-driver",
            "spark-executor",
            "minio",
        ]
        intervals_edge = intervals_edge[
            intervals_edge["pod"].str.startswith(tuple(allowed_prefixes))
        ]

    print(f"Found {len(intervals_edge)} intervals for Edge.")

    # Setup plot - Side by Side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 6), sharey=True)

    # Generate Global Color Map
    all_namespaces = set()
    if not intervals_cloud.empty:
        all_namespaces.update(intervals_cloud["namespace"].unique())
    if not intervals_edge.empty:
        all_namespaces.update(intervals_edge["namespace"].unique())

    # Sort for consistent color assignment across runs
    sorted_namespaces = sorted(list(all_namespaces))
    palette = sns.color_palette("husl", len(sorted_namespaces))
    global_color_map = dict(zip(sorted_namespaces, palette))

    plot_gantt(
        ax1,
        intervals_edge,
        "Edge Environment",
        max_duration,
        global_color_map,
        gaps_edge,
    )
    plot_gantt(
        ax2,
        intervals_cloud,
        "Cloud Environment",
        max_duration,
        global_color_map,
        gaps_cloud,
    )

    plt.tight_layout()
    plt.savefig(OUTPUT_FILE, dpi=400)
    print(f"Chart saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
