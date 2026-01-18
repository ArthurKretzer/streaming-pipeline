import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import os
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

NAMESPACES_OF_INTEREST = ['ingestion', 'spark-jobs', 'deepstorage']

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
    df = df[df['namespace'].isin(namespaces)]
    
    # Filter for Running state
    # We are interested in when the pod is 'Running' (value=1)
    df = df[(df['phase'] == 'Running') & (df['value'] == 1.0)]
    
    return df

def get_pod_intervals(df, start_time_ref):
    """
    Converts time series data into intervals (start, duration) for each pod.
    Returns a list of dicts: {'pod': pod_name, 'start_offset': seconds, 'duration': seconds}
    """
    intervals = []
    
    # Group by pod
    for pod_name, group in df.groupby('pod'):
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
                if duration < 5: duration = 30 
                
                intervals.append({
                    'pod': pod_name,
                    'start_offset': (current_start - start_time_ref).total_seconds(),
                    'duration': duration,
                    'namespace': group['namespace'].iloc[0] # Assume namespace doesn't change
                })
                current_start = time
            
            prev_time = time
            
        # Add the last interval
        duration = (prev_time - current_start).total_seconds()
        if duration < 5: duration = 30
        
        intervals.append({
            'pod': pod_name,
            'start_offset': (current_start - start_time_ref).total_seconds(),
            'duration': duration,
            'namespace': group['namespace'].iloc[0]
        })
            
    return pd.DataFrame(intervals)

def plot_gantt(ax, df_intervals, title, x_limit):
    """Plots a Gantt chart on the given axes."""
    if df_intervals.empty:
        ax.text(0.5, 0.5, "No Running Pods Found", transform=ax.transAxes, ha='center')
        return

    # Assign colors to namespaces
    unique_namespaces = df_intervals['namespace'].unique()
    palette = sns.color_palette("husl", len(unique_namespaces))
    color_map = dict(zip(unique_namespaces, palette))
    
    # Sort pods to group by namespace for better visuals
    df_intervals = df_intervals.sort_values(by=['namespace', 'pod'])
    
    # Map pod names to y-positions
    unique_pods = df_intervals['pod'].unique()
    y_pos = np.arange(len(unique_pods))
    pod_to_y = dict(zip(unique_pods, y_pos))
    
    # Plot bars
    for i, row in df_intervals.iterrows():
        ax.barh(
            y=pod_to_y[row['pod']], 
            width=row['duration'], 
            left=row['start_offset'], 
            height=0.6, 
            color=color_map[row['namespace']],
            edgecolor='none',
            alpha=0.9
        )
        
    ax.set_yticks(y_pos)
    ax.set_yticklabels(unique_pods, fontsize=8)
    ax.set_ylim(-0.5, len(unique_pods) - 0.5)
    ax.set_xlim(0, x_limit)
    ax.set_xlabel("Elapsed Time (s)")
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)

    # Add legend
    handles = [plt.Rectangle((0,0),1,1, color=color_map[ns]) for ns in unique_namespaces]
    ax.legend(handles, unique_namespaces, loc='upper right', fontsize='small')

import re

def simplify_pod_name(pod_name: str) -> str:
    # 1. Handle Spark Executors (preserve number)
    # Pattern: ...-exec-<number>
    match = re.search(r'-exec-(\d+)$', pod_name)
    if match:
        return f"spark-executor-{match.group(1)}"
        
    # 2. Known aliases
    known_aliases = {
        "alertmanager-monitoring-alertmanager-0": "prometheus-alerts",
        "argocd-application-controller-1": "argocd-controller-1",
        "argocd-application-controller-0": "argocd-controller-0",
        "argocd-notifications-controller": "argocd-notifications-controller",
        "argocd-applicationset-controller": "argocd-controller",
        "argocd-redis" : "argocd-redis",
        "argocd-repo-server" : "argocd-repo-server",
        "argocd-server" : "argocd-server",
        "ntp-configurator" : "ntp-sync",
        'coredns': 'coredns',
        'svclb-traefik': 'traefik',
        "traefik" : "traefik",
        'local-path-provisioner': 'local-path-provisioner',
        'metrics-server': 'metrics-server',
        'minio-community': 'minio',
        'monitoring-operator': 'monitoring-operator',
        "prometheus-monitoring-prometheus-0": "prometheus",
        "kube-prometheus-stack-prometheus-node-exporter": "prometheus",
        "kube-prometheus-stack-kube-state-metrics": "prometheus",
        "streaming-cruise-control" : "kafka-cruise-control",
        "master-cruise-control" : "kafka-cruise-control",
        "argocd-dex-server" : "argocd-dex-server",
        "kube-prometheus-stack-grafana-0": "grafana",
        "streaming-kafka-2" : "kafka-broker-2",
        "streaming-kafka-0" : "kafka-broker-0",
        "streaming-kafka-1" : "kafka-broker-1",
        "streaming-kafka-3" : "kafka-broker-3",
        "master-kafka-2" : "kafka-broker-2",
        "master-kafka-0" : "kafka-broker-0",
        "master-kafka-1" : "kafka-broker-1",
        "master-kafka-3" : "kafka-broker-3",
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
        "cpc-bridge-proxy" : "do-resources",
        "csi-do-node" : "do-resources",
        "do-node-agent" : "do-resources",
        "konnectivity-agent" : "do-resources",
        "hubble-relay" : "do-resources",
        "hubble-ui" : 'do-resources',
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
    df_cloud = load_and_filter_data(CLOUD_PATH, start_cloud, end_cloud, NAMESPACES_OF_INTEREST)
    intervals_cloud = get_pod_intervals(df_cloud, start_cloud)
    if not intervals_cloud.empty:
        intervals_cloud['pod'] = intervals_cloud['pod'].apply(simplify_pod_name)
        # Filter for interested pods
        allowed_prefixes = ['kafka-broker', 'zookeeper', 'spark-driver', 'spark-executor', 'minio']
        intervals_cloud = intervals_cloud[intervals_cloud['pod'].str.startswith(tuple(allowed_prefixes))]
        
    print(f"Found {len(intervals_cloud)} intervals for Cloud.")

    print("Loading Edge Data...")
    df_edge = load_and_filter_data(EDGE_PATH, start_edge, end_edge, NAMESPACES_OF_INTEREST)
    intervals_edge = get_pod_intervals(df_edge, start_edge)
    if not intervals_edge.empty:
        intervals_edge['pod'] = intervals_edge['pod'].apply(simplify_pod_name)
        allowed_prefixes = ['kafka-broker', 'zookeeper', 'spark-driver', 'spark-executor', 'minio']
        intervals_edge = intervals_edge[intervals_edge['pod'].str.startswith(tuple(allowed_prefixes))]
        
    print(f"Found {len(intervals_edge)} intervals for Edge.")
    
    # Setup plot - Side by Side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 6), sharey=True)
    
    # Common Y-axis (Union of pods) to ensure alignment if sharing Y
    # To make sharey work nicely, we should ideally have the same Y-axis categories.
    # But for now, let's just plot them. If sharey=True, matplotlib handles it but might mask missing ones on one side.
    # Let's trust sharey=True with the filtered list which should be very similar.
    
    plot_gantt(ax1, intervals_cloud, "Cloud Environment", max_duration)
    plot_gantt(ax2, intervals_edge, "Edge Environment", max_duration)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_FILE, dpi=400)
    print(f"Chart saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
