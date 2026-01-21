import re

import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np
import pandas as pd
import pytz
import seaborn as sns
from matplotlib.patches import Patch
from utils import get_true_spark_run_starts, simplify_pod_name

NODE_CPU_LIMITS = {
    "flncpcsrv-k8s-w01": 400,
    "flncpcsrv-k8s-w02": 400,
    "flncpcsrv-k8s-w03": 400,
    "flncpcsrv-k8s-w04": 400,
    "flncpcsrv-k8s-w11": 800,
}

NODE_MEMORY_LIMITS = {
    "flncpcsrv-k8s-w01": 16.384,  # 16 GiB
    "flncpcsrv-k8s-w02": 16.384,
    "flncpcsrv-k8s-w03": 16.384,
    "flncpcsrv-k8s-w04": 16.384,
    "flncpcsrv-k8s-w11": 40.960,  # 40 GiB
}


def calculate_rate(
    df: pd.DataFrame,
    value_col="value",
    columns: list[str] = ["kubernetes_pod_name", "topic"],
) -> pd.Series:
    """Calculates the rate per second for counter metrics."""
    # Group by labels (topic, instance, etc.) to calculate rates correctly
    group_cols = columns

    def get_rate(group):
        # Rate = (val_t2 - val_t1) / (time_t2 - time_t1 in seconds)
        delta_val = group[value_col].diff()
        delta_time = group.index.to_series().diff().dt.total_seconds()

        # Avoid division by zero if timestamps are duplicate
        delta_time = delta_time.replace(0, pd.NA).fillna(1.0)

        rate = delta_val / delta_time

        # Handle Prometheus counter resets
        reset_mask = delta_val < 0
        if reset_mask.any():
            rate.loc[reset_mask] = (
                group.loc[reset_mask, value_col] / delta_time.loc[reset_mask]
            )

        return rate

    return df.groupby(group_cols, group_keys=False).apply(get_rate)


def annotate_spark_starts(
    ax,
    df,
    df_status,
    node=None,
    pod_color_map=None,
    top_offset=0.5,
    top_offset_inc=0.2,
    label_offset_secs=60,
):
    """
    Annotates spark driver/executor start times on a matplotlib axis.

    Parameters:
        ax (matplotlib.axes.Axes): The axis to annotate.
        df (pd.DataFrame): The full CPU or metric DataFrame with 'timestamp', 'pod', 'node'.
        node (str): Node name for filtering.
        pod_color_map (dict): Maps pod name to color.
        top_offset (float): Vertical placement (fraction of y-axis height).
        label_offset_secs (int): Time offset for text label placement (in seconds).
    """

    def format_spark_label(pod_name):
        if "driver" in pod_name:
            return "Driver"
        elif "exec" in pod_name:
            return f"Exc-{pod_name.split('-exec-')[-1]}"
        return pod_name  # fallback

    spark_pod_starts = get_true_spark_run_starts(df_status)

    spark_pod_starts.sort_values(["timestamp", "pod"])

    # Create a color map if not provided
    if pod_color_map is None:
        unique_pods = spark_pod_starts["pod"].unique()
        cmap = plt.get_cmap("tab10", len(unique_pods))  # or 'Set1', 'tab20'
        pod_color_map = {
            pod: mcolors.to_hex(cmap(i)) for i, pod in enumerate(unique_pods)
        }

    for pod, ts in spark_pod_starts.itertuples(index=False):
        if pod not in pod_color_map:
            continue
        if node:
            pod_node_df = df[(df["pod"] == pod) & (df["node"] == node)]
            if pod_node_df.empty:
                continue

        color = pod_color_map[pod]
        label_text = format_spark_label(pod)

        ax.axvline(x=ts, color=color, linestyle="-.", linewidth=1.5)

        ymin, ymax = ax.get_ylim()
        y_pos = ymin + (ymax - ymin) * top_offset

        ax.text(
            ts + pd.Timedelta(seconds=label_offset_secs),
            y_pos,
            label_text,
            rotation=90,
            fontsize=8,
            color=color,
            ha="left",
            va="top",
            bbox=dict(
                facecolor="white",
                edgecolor="none",
                alpha=0.6,
                boxstyle="round,pad=0.2",
            ),
        )
        top_offset += top_offset_inc


def cpu_chart(
    df: pd.DataFrame,
    df_status: pd.DataFrame,
    title: str = "CPU Usage by Pod",
    node_cpu_limits=NODE_CPU_LIMITS,
):
    # Define your desired timezone
    local_tz = pytz.timezone("America/Sao_Paulo")

    df = df.sort_values(by=["id", "pod", "timestamp"]).dropna(subset="container")
    # df["pod"] = df["pod"].apply(simplify_pod_name)
    # df_status["pod"] = df_status["pod"].apply(simplify_pod_name)

    # Calculate diffs and remove resets
    # Calculate diffs and remove resets using calculate_rate
    # Ensure timestamp is index for calculate_rate
    df = df.set_index("timestamp")
    df["rate"] = calculate_rate(df, columns=["id"])

    # Convert rate to percentage (if needed - original code did * 100)
    # The original code was: (val_diff / time_diff) * 100
    # calculate_rate returns val_diff / time_diff per second.
    # So we multiply by 100 to get percentage (assuming value is CPU seconds and we want percent of a core? Or usage in some unit?)
    # Original: (df["value_diff"] / df["time_diff"]) * 100
    df["rate"] = df["rate"] * 100

    # Reset index to get timestamp back as column
    df = df.reset_index()

    # Filter out NaNs/Inf if any
    df = df.dropna(subset=["rate"])

    df["cpu_percent"] = df.groupby("pod")["rate"].transform(
        lambda x: x.rolling(window=3, min_periods=1).mean()
    )

    # === Step 2: Clip CPU usage based on node limits ===
    df["cpu_limit"] = df["node"].map(node_cpu_limits)

    # === Step 3: Assign consistent categorical colors to pods ===
    unique_pods = sorted(df["pod"].unique())
    palette = plt.get_cmap("tab20")  # can use 'Set1', 'Dark2', etc. for more contrast
    colors = [palette(i % palette.N) for i in range(len(unique_pods))]
    pod_color_map = dict(zip(unique_pods, colors))

    # === Step 4: Plot CPU usage by node with consistent colors ===
    fig, axes = plt.subplots(nrows=3, ncols=2, figsize=(18, 12), sharex=False)
    axes = axes.flatten()

    for i, node in enumerate(node_cpu_limits.keys()):
        ax = axes[i]
        node_data = df[df["node"] == node]

        for pod_name, pod_df in node_data.groupby("pod"):
            ax.plot(
                pod_df["timestamp"],
                pod_df["cpu_percent"],
                label=pod_name,
                color=pod_color_map[pod_name],
            )

        ax.set_title(f"CPU Usage on {node}")
        ax.set_ylabel("CPU Usage (%)")
        ax.axhline(
            y=node_cpu_limits[node],
            color="red",
            linestyle="--",
            label="CPU Limit",
        )

        # === Reusable annotation call ===
        annotate_spark_starts(ax, df, df_status, node, pod_color_map)

        ax.legend(loc="upper right", fontsize="x-small")
        ax.grid(True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=local_tz))

    # Hide unused subplot
    if len(axes) > len(node_cpu_limits):
        for j in range(len(node_cpu_limits), len(axes)):
            fig.delaxes(axes[j])

    axes[-1].set_xlabel("Time")
    fig.suptitle(title, fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()


def cpu_chart_stacked(
    df: pd.DataFrame,
    node_cpu_limits={},
    title: str = "CPU Usage by Pod",
    save_path: str = None,
):
    # === Step 1: Preprocess Raw Data ===
    df = df.sort_values(by=["id", "pod", "timestamp"]).dropna(subset="container")
    df["pod"] = df["pod"].apply(simplify_pod_name)

    # Use calculate_rate
    df = df.set_index("timestamp")
    df["rate"] = calculate_rate(df, columns=["id"])
    df["rate"] = df["rate"] * 100
    df = df.reset_index().dropna(subset=["rate"])

    df["cpu_percent"] = df.groupby("pod")["rate"].transform(
        lambda x: x.rolling(window=3, min_periods=1).mean()
    )

    df["cpu_limit"] = df["node"].map(node_cpu_limits)

    # === Step 2: Keep only necessary columns and resample ===
    df_resampled = (
        df[["timestamp", "node", "pod", "cpu_percent"]]
        .set_index("timestamp")
        .groupby(["node", "pod"])
        .resample("30s")
        .mean(numeric_only=True)  # Ensures only numeric values are averaged
        .reset_index()
    )

    df_resampled["relative_time"] = (
        df_resampled["timestamp"] - df_resampled["timestamp"].min()
    ).dt.total_seconds()

    # === Step 3: Plotting Setup ===
    unique_pods = sorted(df_resampled["pod"].unique())
    # Combine tab20, tab20b, and tab20c to provide 60 distinct colors
    palette = (
        list(plt.get_cmap("tab20").colors)
        + list(plt.get_cmap("tab20b").colors)
        + list(plt.get_cmap("tab20c").colors)
    )
    pod_color_map = {
        pod: palette[i % len(palette)] for i, pod in enumerate(unique_pods)
    }

    fig, axes = plt.subplots(nrows=3, ncols=2, figsize=(18, 12), sharex=True)
    axes = axes.flatten()

    for i, node in enumerate(node_cpu_limits.keys()):
        ax = axes[i]
        node_data = df_resampled[df_resampled["node"] == node]

        if node_data.empty:
            ax.set_visible(False)
            continue

        pivot_df = (
            node_data.pivot_table(
                index="relative_time",
                columns="pod",
                values="cpu_percent",
                aggfunc="mean",
            )
            .fillna(0)
            .sort_index()
        )

        present_pods = pivot_df.columns.tolist()
        colors_present = [pod_color_map[pod] for pod in present_pods]

        ax.stackplot(
            pivot_df.index,
            pivot_df.T.values,
            labels=present_pods,
            colors=colors_present,
        )

        ax.set_title(f"CPU Usage on {node}")
        ax.set_ylabel("CPU Usage (%)")
        ax.axhline(
            y=node_cpu_limits[node],
            color="red",
            linestyle="--",
            label="CPU Limit",
        )

        # === Reusable annotation call ===
        # annotate_spark_starts(ax, df, df_status, node, pod_color_map)

        # === LEGEND FILTERING: SHOW ONLY TOP OFFENDERS ===
        # Calculate mean CPU usage to identify top offenders
        top_n = 5
        pod_means = pivot_df.mean().sort_values(ascending=False)
        top_offenders = pod_means.head(top_n).index.tolist()

        handles, labels = ax.get_legend_handles_labels()
        filtered_handles = []
        filtered_labels = []

        for h, l in zip(handles, labels):
            # Keep "CPU Limit" and the top N pods
            if l == "CPU Limit" or l in top_offenders:
                filtered_handles.append(h)
                filtered_labels.append(l)

        ax.legend(
            filtered_handles,
            filtered_labels,
            loc="upper right",
            fontsize="x-small",
            ncol=2,
        )
        ax.grid(True)

    # Hide unused subplots
    for j in range(len(node_cpu_limits), len(axes)):
        fig.delaxes(axes[j])

    axes[-1].set_xlabel("Time")
    fig.suptitle(title, fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def cpu_chart_nodes(
    df_edge: pd.DataFrame,
    df_cloud: pd.DataFrame,
    title: str = "Total CPU Usage per Node",
    max_cpu: int = 4,
    save_path: str = None,
):
    # === Helper to process CPU dataframe ===
    def process_cpu_df(df):
        df = df[df["node"] != "server-k8s-m01"]

        df = (
            df.sort_values(by=["id", "pod", "timestamp"])
            .dropna(subset="container")
            .copy()
        )

        # Use calculate_rate
        df = df.set_index("timestamp")
        df["rate"] = calculate_rate(df, columns=["id"])
        df["rate"] = df["rate"] * 100
        df = df.reset_index().dropna(subset=["rate"])

        df["cpu_percent"] = df.groupby("pod")["rate"].transform(
            lambda x: x.rolling(window=3, min_periods=1).mean()
        )

        df_resampled = (
            df[["timestamp", "node", "pod", "cpu_percent"]]
            .set_index("timestamp")
            .groupby(["node", "pod"])
            .resample("30s")
            .mean(numeric_only=True)
            .reset_index()
        )

        # Sum CPU usage per node and timestamp
        df_node_total_cpu = (
            df_resampled.groupby(["timestamp", "node"])["cpu_percent"]
            .sum()
            .unstack(level="node")
            .fillna(0)
        )

        df_node_total_cpu.index = (
            df_node_total_cpu.index - df_node_total_cpu.index.min()
        ).total_seconds()

        return df_node_total_cpu

    # === Process both environments ===
    df_node_total_edge = process_cpu_df(df_edge)
    df_node_total_cloud = process_cpu_df(df_cloud)

    # === Plotting ===
    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(14, 12), sharex=False)

    datasets = [("Edge", df_node_total_edge), ("Cloud", df_node_total_cloud)]

    for ax, (env_name, df_node_total) in zip(axes, datasets):
        for node in df_node_total.columns:
            ax.plot(df_node_total.index, df_node_total[node], label=node)

        ax.axhline(
            y=max_cpu * 100,
            color="red",
            linestyle="--",
            label=f"Max CPU ({max_cpu})",
        )

        ax.set_title(f"{env_name} - {title}")
        ax.set_ylabel("CPU Usage (%)")
        ax.legend(title="Node", loc="upper right")
        ax.grid(True)

    axes[-1].set_xlabel("Time Elased (s)")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def memory_chart(
    df: pd.DataFrame,
    df_status: pd.DataFrame,
    title: str = "Memory Usage by Pod",
    node_memory_limits=NODE_MEMORY_LIMITS,
    save_path: str = None,
):
    # Define your desired timezone
    local_tz = pytz.timezone("America/Sao_Paulo")

    memory_df = (
        df.sort_values(by=["pod", "timestamp"]).dropna(subset="container").copy()
    )

    # Convert from bytes to MiB
    memory_df["memory_gib"] = memory_df["value"] / (1024 * 1024 * 1024)  # Gib

    # Apply 3-point rolling average to smooth
    memory_df["memory_gib_smoothed"] = memory_df.groupby("pod")["memory_gib"].transform(
        lambda x: x.rolling(window=3, min_periods=1).mean()
    )

    memory_df["memory_limit"] = memory_df["node"].map(node_memory_limits)

    # === Step 2: Assign consistent categorical colors to pods ===
    unique_pods = sorted(memory_df["pod"].unique())
    palette = plt.get_cmap("tab20")
    colors = [palette(i % palette.N) for i in range(len(unique_pods))]
    pod_color_map = dict(zip(unique_pods, colors))

    # === Step 3: Plot smoothed memory usage by node ===
    fig, axes = plt.subplots(nrows=3, ncols=2, figsize=(18, 12), sharex=False)
    axes = axes.flatten()

    for i, node in enumerate(node_memory_limits.keys()):
        ax = axes[i]
        node_data = memory_df[memory_df["node"] == node]

        for pod_name, pod_df in node_data.groupby("pod"):
            ax.plot(
                pod_df["timestamp"],
                pod_df["memory_gib_smoothed"],
                label=pod_name,
                color=pod_color_map[pod_name],
            )

        ax.set_title(f"Memory Usage on {node}")
        ax.set_ylabel("Memory Usage (GiB)")
        ax.legend(loc="upper right", fontsize="x-small")

        ax.axhline(
            y=node_memory_limits[node],
            color="red",
            linestyle="--",
            label="Memory Limit",
        )

        # === Reusable annotation call ===
        annotate_spark_starts(ax, memory_df, df_status, node, pod_color_map)

        ax.grid(True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=local_tz))

    # Hide any unused subplot
    if len(axes) > len(node_memory_limits):
        for j in range(len(node_memory_limits), len(axes)):
            fig.delaxes(axes[j])

    axes[-1].set_xlabel("Time")
    fig.suptitle(title, fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def memory_chart_stacked(
    df: pd.DataFrame,
    title: str = "Memory Usage by Pod",
    node_memory_limits={},
    save_path: str = None,
):
    # === Step 1: Preprocessing ===
    memory_df = (
        df.sort_values(by=["timestamp", "pod"]).dropna(subset="container").copy()
    )
    # Simplify pod names
    memory_df["pod"] = memory_df["pod"].apply(simplify_pod_name)

    # Convert bytes to MiB
    memory_df["memory_gib"] = memory_df["value"] / (1024 * 1024 * 1024)  # Gib

    # Smooth using rolling average
    # memory_df["memory_gib_smoothed"] = memory_df.groupby("pod")["memory_gib"].transform(
    #     lambda x: x.rolling(window=3, min_periods=1).mean()
    # )

    memory_df["memory_limit"] = memory_df["node"].map(node_memory_limits)

    # === Step 2: Resample every 30 seconds ===
    # Use raw memory_gib instead of smoothed
    memory_resampled = (
        memory_df[["timestamp", "node", "pod", "memory_gib"]]
        .set_index("timestamp")
        .groupby(["node", "pod"])
        .resample("30s")
        .mean(numeric_only=True)
        .reset_index()
    )

    memory_resampled["relative_time"] = (
        memory_resampled["timestamp"] - memory_resampled["timestamp"].min()
    ).dt.total_seconds()

    # === Step 3: Color Palette ===
    unique_pods = sorted(memory_df["pod"].unique())
    # Combine tab20, tab20b, and tab20c to provide 60 distinct colors
    palette = (
        list(plt.get_cmap("tab20").colors)
        + list(plt.get_cmap("tab20b").colors)
        + list(plt.get_cmap("tab20c").colors)
    )
    pod_color_map = {
        pod: palette[i % len(palette)] for i, pod in enumerate(unique_pods)
    }

    # === Step 4: Plotting ===
    fig, axes = plt.subplots(nrows=3, ncols=2, figsize=(18, 12), sharex=False)
    axes = axes.flatten()

    for i, node in enumerate(node_memory_limits.keys()):
        ax = axes[i]
        node_data = memory_resampled[memory_resampled["node"] == node]

        if node_data.empty:
            ax.set_visible(False)
            continue

        pivot_df = (
            node_data.pivot_table(
                index="relative_time",
                columns="pod",
                values="memory_gib",
                aggfunc="mean",
            )
            .fillna(0)
            .sort_index()
        )

        # === Sort pods by "Top Offender" (Max Usage) ===
        pod_max = pivot_df.max().sort_values(ascending=False)
        sorted_pods = pod_max.index.tolist()

        # Reorder DataFrame and Colors
        pivot_df = pivot_df[sorted_pods]
        colors_present = [
            pod_color_map[pod] for pod in sorted_pods if pod in pod_color_map
        ]

        ax.stackplot(
            pivot_df.index,
            pivot_df.T.values,
            labels=sorted_pods,
            colors=colors_present,
        )

        ax.set_title(f"Memory Usage on {node}")
        ax.set_ylabel("Memory Usage (GiB)")
        ax.axhline(
            y=node_memory_limits[node],
            color="red",
            linestyle="--",
            label="Memory Limit",
        )

        # === Reusable annotation call ===
        # annotate_spark_starts(ax, memory_df, df_status, node, pod_color_map)

        # === LEGEND FILTERING: SHOW ONLY TOP OFFENDERS ===
        # Calculate mean Memory usage to identify top offenders
        top_n = 5
        pod_means = pivot_df.mean().sort_values(ascending=False)
        top_offenders = pod_means.head(top_n).index.tolist()

        handles, labels = ax.get_legend_handles_labels()
        filtered_handles = []
        filtered_labels = []

        for h, l in zip(handles, labels):
            # Keep "Memory Limit" and the top N pods
            if l == "Memory Limit" or l in top_offenders:
                filtered_handles.append(h)
                filtered_labels.append(l)

        ax.legend(
            filtered_handles,
            filtered_labels,
            loc="upper right",
            fontsize="x-small",
            ncol=2,
        )
        ax.grid(True)

    # Remove unused plots
    for j in range(len(node_memory_limits), len(axes)):
        fig.delaxes(axes[j])

    axes[-1].set_xlabel("Elapsed Time (s)")
    fig.suptitle(title, fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def memory_chart_nodes(
    df_edge: pd.DataFrame,
    df_cloud: pd.DataFrame,
    title: str = "Total Memory Usage per Node",
    save_path: str = None,
):
    # === Helper to process Memory dataframe ===
    def process_memory_df(df):
        if df.empty:
            return pd.DataFrame()

        # Filter master node
        df = df[df["node"] != "server-k8s-m01"]

        memory_df = (
            df.sort_values(by=["timestamp", "pod"]).dropna(subset="container").copy()
        )

        # Simplify pod names (good for consistency)
        memory_df["pod"] = memory_df["pod"].apply(simplify_pod_name)

        # Convert bytes to GiB
        memory_df["memory_gib"] = memory_df["value"] / (1024**3)

        # Smooth
        # memory_df["memory_gib_smoothed"] = memory_df.groupby("pod")["memory_gib"].transform(
        #     lambda x: x.rolling(window=3, min_periods=1).mean()
        # )

        # Aggregate by node and resample
        memory_df["node"] = memory_df["node"].astype(str)

        memory_resampled = (
            memory_df[["timestamp", "node", "pod", "memory_gib"]]
            .set_index("timestamp")
            .groupby(["node", "pod"])
            .resample("30s")
            .mean(numeric_only=True)
            .reset_index()
        )

        # Calculate Relative Time (Elapsed Seconds)
        start_time = memory_resampled["timestamp"].min()
        memory_resampled["relative_time"] = (
            memory_resampled["timestamp"] - start_time
        ).dt.total_seconds()

        total_mem_per_node = (
            memory_resampled.groupby(["relative_time", "node"])["memory_gib"]
            .sum()
            .unstack(level="node")
            .fillna(0)
        )
        return total_mem_per_node

    # === Process both environments ===
    df_node_total_edge = process_memory_df(df_edge)
    df_node_total_cloud = process_memory_df(df_cloud)

    # === Plotting ===
    # Sharex=True allows comparing timeline if they have similar duration
    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(14, 12), sharex=False)

    datasets = [("Edge", df_node_total_edge), ("Cloud", df_node_total_cloud)]

    for ax, (env_name, df_node_total) in zip(axes, datasets):
        if df_node_total.empty:
            ax.text(0.5, 0.5, "No Data", ha="center", va="center")
            ax.set_title(f"{env_name} - {title}")
            continue

        # Sort nodes by "Top Offender" (Max Usage)
        node_max = df_node_total.max().sort_values(ascending=False)
        sorted_nodes = node_max.index.tolist()

        for node in sorted_nodes:
            ax.plot(df_node_total.index, df_node_total[node], label=node)

        ax.axhline(
            y=8.192,
            color="red",
            linestyle="--",
            label="Memory Limit (8 GiB)",
        )

        ax.set_title(f"{env_name} - {title}")
        ax.set_ylabel("Memory Usage (GiB)")
        ax.legend(title="Node", loc="upper right")
        ax.grid(True)

    axes[-1].set_xlabel("Elapsed Time (s)")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def gantt_chart(
    df_status: pd.DataFrame,
    title="Pod Exeution Gantt Chart",
    save_path: str = None,
):
    # Define your desired timezone
    local_tz = pytz.timezone("America/Sao_Paulo")

    # Only active status
    df = df_status[df_status["value"] == 1.0].copy()
    df = df.sort_values(["pod", "timestamp"])

    # === Step 1: Group definitions ===
    group_definitions = {
        "MinIO": ["minio-community", "minio-master"],
        "Kafka": [
            "labfaber-cruise-control",
            "streaming-kafka",
            "streaming-kafka-schema-registry",
            "streaming-kafka-ui",
            "labfaber-zookeeper",
            "master-cruise-control",
            "master-kafka",
            "master-kafka-schema-registry",
            "master-kafka-ui",
            "master-zookeeper",
            "strimzi-cluster-operator",
        ],
        "Spark": [
            "deltalakewithminio",
            "deploy-spark-history-server",
            "streaming-pipeline-kafka-avro-to-delta-driver",
            "spark-operator-controller",
            "spark-operator-webhook",
        ],
    }

    phase_colors = {
        "Running": "green",
        "Pending": "orange",
        "Failed": "red",
        "Succeeded": "blue",
        "Unknown": "gray",
    }

    fig, axes = plt.subplots(nrows=3, figsize=(18, 14), sharex=False)

    for ax, (group_name, prefixes) in zip(axes, group_definitions.items()):
        group_df = df[
            df["pod"].apply(lambda p: any(p.startswith(prefix) for prefix in prefixes))
        ].copy()

        # Assign y positions
        unique_pods = sorted(group_df["pod"].unique())
        pod_to_y = {pod: i for i, pod in enumerate(unique_pods)}

        # Track segments
        seen_phases = set()

        for pod in unique_pods:
            pod_df = group_df[group_df["pod"] == pod].copy()

            pod_df["phase_shift"] = (
                pod_df["phase"] != pod_df["phase"].shift()
            ).cumsum()
            for _, seg in pod_df.groupby("phase_shift"):
                if seg.empty:
                    continue
                phase = seg["phase"].iloc[0]
                label = phase if phase not in seen_phases else None
                seen_phases.add(phase)

                start = seg["timestamp"].iloc[0]
                end = seg["timestamp"].iloc[-1]
                ax.hlines(
                    y=pod_to_y[pod],
                    xmin=start,
                    xmax=end,
                    colors=phase_colors.get(phase, "black"),
                    linewidth=6,
                    label=label,
                )

        ax.set_yticks(list(pod_to_y.values()))
        ax.set_yticklabels(list(pod_to_y.keys()))
        ax.set_title(f"{group_name} Pods Status Over Time")
        ax.set_ylabel("Pods")
        ax.grid(True, axis="x")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=local_tz))

    fig.suptitle(title, fontsize=24)

    # Label and legend
    axes[-1].set_xlabel("Time")
    handles, labels = axes[0].get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    axes[0].legend(by_label.values(), by_label.keys(), title="Phase", loc="upper right")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def minio_charts(
    df_minio_total: pd.DataFrame,
    df_minio_errors: pd.DataFrame,
    df_minio_waiting: pd.DataFrame,
    df_minio_sent_bytes: pd.DataFrame,
    df_minio_received_bytes: pd.DataFrame,
    df_cpu: pd.DataFrame,
    df_status: pd.DataFrame,
    title: str = "Minio Charts",
    save_path: str = None,
):
    # Define your desired timezone
    local_tz = pytz.timezone("America/Sao_Paulo")

    # === Process counter-based metrics to smoothed rate ===
    def process_rate(df):
        df = df.sort_values(by=["timestamp", "pod"]).dropna(subset="container")
        df["value_diff"] = df.groupby("pod")["value"].diff()
        df["time_diff"] = df.groupby("pod")["timestamp"].diff().dt.total_seconds()
        df = df[(df["value_diff"] >= 0) & (df["time_diff"] > 0)].copy()
        df["rate"] = df["value_diff"] / df["time_diff"]
        df["rate_smoothed"] = df.groupby("pod")["rate"].transform(
            lambda x: x.rolling(window=3, min_periods=1).mean()
        )
        return df

    def aggregate_and_process(df):
        df = df.sort_values(by=["timestamp", "pod"])
        df = df.groupby(["timestamp", "pod", "container"], as_index=False)[
            "value"
        ].sum()
        df = process_rate(df)
        return df

    # === Apply processing ===
    df_total_proc = aggregate_and_process(df_minio_total)
    df_errors_proc = aggregate_and_process(df_minio_errors)
    df_waiting_proc = aggregate_and_process(df_minio_waiting)
    df_sent_proc = process_rate(df_minio_sent_bytes)
    df_sent_proc["rate_smoothed"] /= 1024  # Bytes → KiB
    df_received_proc = process_rate(df_minio_received_bytes)
    df_received_proc["rate_smoothed"] /= 1024  # Bytes → KiB

    # === Load and process CPU usage ===
    cpu_df = (
        df_cpu.sort_values(by=["id", "pod", "timestamp"])
        .dropna(subset="container")
        .copy()
    )
    cpu_df["value_diff"] = cpu_df.groupby("id")["value"].diff()
    cpu_df["time_diff"] = cpu_df.groupby("id")["timestamp"].diff().dt.total_seconds()
    cpu_df = cpu_df[(cpu_df["value_diff"] > 0) & (cpu_df["time_diff"] > 0)].copy()
    cpu_df["rate"] = (cpu_df["value_diff"] / cpu_df["time_diff"]) * 100
    cpu_df["cpu_percent_smoothed"] = cpu_df.groupby("pod")["rate"].transform(
        lambda x: x.rolling(window=3, min_periods=1).mean()
    )
    minio_cpu_df = cpu_df[
        cpu_df["pod"].str.startswith("minio-community")
        | cpu_df["pod"].str.startswith("minio-master")
    ].copy()

    # === Detect actual pod restart cycles: Pending → Running ===
    status_df = df_status[
        df_status["pod"].str.startswith("minio-community")
        | df_status["pod"].str.startswith("minio-master")
    ].copy()
    status_df = status_df[status_df["value"] == 1.0].sort_values(["pod", "timestamp"])

    restart_events = []

    for pod, pod_df in status_df.groupby("pod"):
        pod_df = pod_df.reset_index(drop=True)
        for i in range(1, len(pod_df)):
            prev_row = pod_df.iloc[i - 1]
            curr_row = pod_df.iloc[i]

            if prev_row["phase"] != "Pending" and curr_row["phase"] == "Pending":
                # Start of a restart
                restart_time = curr_row["timestamp"]

                # Find next running status
                running_rows = pod_df[
                    (pod_df["timestamp"] > restart_time)
                    & (pod_df["phase"] == "Running")
                ]
                if not running_rows.empty:
                    running_time = running_rows.iloc[0]["timestamp"]
                else:
                    running_time = None

                restart_events.append(
                    {
                        "pod": pod,
                        "restart_time": restart_time,
                        "running_time": running_time,
                    }
                )

    restarts_df = pd.DataFrame(restart_events)

    # === Helper to plot metric + CPU + annotations ===
    def plot_with_cpu_overlay(ax, metric_df, cpu_df, title, ylabel_left):
        ax
        for pod, pod_df in metric_df.groupby("pod"):
            ax.plot(
                pod_df["timestamp"],
                pod_df["rate_smoothed"],
                label=pod,
                alpha=0.7,
            )
        ax.set_ylabel(ylabel_left)
        ax.grid(True)

        # Right axis for CPU
        ax_right = ax.twinx()
        for pod, pod_df in cpu_df.groupby("pod"):
            ax_right.plot(
                pod_df["timestamp"],
                pod_df["cpu_percent_smoothed"],
                linestyle="--",
                alpha=0.4,
                label=f"{pod} CPU",
            )
        ax_right.set_ylabel("CPU %")

        # Restart annotations (Pending + Running)
        for _, row in restarts_df.iterrows():
            pod = row["pod"]
            restart_time = row["restart_time"]
            running_time = row["running_time"]

            if restart_time:
                ax.axvline(x=restart_time, color="red", linestyle=":", alpha=0.7)
                ax.text(
                    restart_time + pd.Timedelta(seconds=10),
                    ax.get_ylim()[1],
                    f"{pod} Restart",
                    color="red",
                    fontsize=8,
                    rotation=90,
                    verticalalignment="top",
                )

            if pd.notna(running_time):
                ax.axvline(x=running_time, color="green", linestyle=":", alpha=0.7)
                ax.text(
                    running_time + pd.Timedelta(seconds=10),
                    ax.get_ylim()[1],
                    f"{pod} Running",
                    color="green",
                    fontsize=8,
                    rotation=90,
                    verticalalignment="top",
                )

        annotate_spark_starts(
            ax,
            metric_df,
            df_status,
            top_offset=0.15,
            top_offset_inc=0.1,
            label_offset_secs=10,
        )

        ax.set_title(title)
        return ax, ax_right

    # === Generate 5-panel figure ===
    fig, axes = plt.subplots(nrows=5, figsize=(18, 22), sharex=False)

    plot_with_cpu_overlay(
        axes[0],
        df_total_proc,
        minio_cpu_df,
        "MinIO S3 Requests/sec by Pod",
        "Requests/sec",
    )
    plot_with_cpu_overlay(
        axes[1],
        df_errors_proc,
        minio_cpu_df,
        "MinIO S3 Error Rate/sec by Pod",
        "Errors/sec",
    )
    plot_with_cpu_overlay(
        axes[2],
        df_waiting_proc,
        minio_cpu_df,
        "MinIO S3 Waiting Requests/sec by Pod",
        "Waiting/sec",
    )
    plot_with_cpu_overlay(
        axes[3],
        df_sent_proc,
        minio_cpu_df,
        "MinIO S3 Traffic Sent (KiB/sec) by Pod",
        "KiB/sec",
    )
    plot_with_cpu_overlay(
        axes[4],
        df_received_proc,
        minio_cpu_df,
        "MinIO S3 Traffic Received (KiB/sec) by Pod",
        "KiB/sec",
    )

    fig.suptitle(title, fontsize=24)

    axes[-1].set_xlabel("Time")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=local_tz))
    axes[0].legend(loc="upper right", fontsize="x-small", title="Pods")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def kafka_charts(
    kafka_bytes_in: pd.DataFrame,
    kafka_bytes_out: pd.DataFrame,
    kafka_requests: pd.DataFrame,
    kafka_requests_errors: pd.DataFrame,
    kafka_messages_in: pd.DataFrame,
    df_cpu: pd.DataFrame,
    df_status: pd.DataFrame,
    title: str = "Kafka Charts",
    save_path: str = None,
):
    # Define your desired timezone
    local_tz = pytz.timezone("America/Sao_Paulo")

    def process_rate(df):
        df = df.sort_values(by=["timestamp", "pod"]).dropna(subset=["container"])
        df["value_diff"] = df.groupby("pod")["value"].diff()
        df["time_diff"] = df.groupby("pod")["timestamp"].diff().dt.total_seconds()
        df = df[(df["value_diff"] >= 0) & (df["time_diff"] > 0)].copy()
        df["rate"] = df["value_diff"] / df["time_diff"]
        df["rate_smoothed"] = df.groupby("pod")["rate"].transform(
            lambda x: x.rolling(window=3, min_periods=1).mean()
        )
        return df

    def aggregate_and_process(df):
        df = df.sort_values(by=["timestamp", "pod"])
        df = df.groupby(["timestamp", "pod", "container"], as_index=False)[
            "value"
        ].sum()
        return process_rate(df)

    def annotate_kafka_restarts(ax, restart_df):
        for _, row in restart_df.iterrows():
            try:
                ax.axvline(
                    x=row["restart_time"],
                    color="red",
                    linestyle=":",
                    alpha=0.7,
                )
                ax.text(
                    row["restart_time"] + pd.Timedelta(seconds=10),
                    ax.get_ylim()[1],
                    f"{row['pod']} Restart",
                    color="red",
                    fontsize=8,
                    rotation=90,
                    verticalalignment="top",
                )
            except KeyError:
                pass
            try:
                ax.axvline(
                    x=row["start_time"],
                    color="green",
                    linestyle=":",
                    alpha=0.7,
                )
                ax.text(
                    row["start_time"] + pd.Timedelta(seconds=10),
                    ax.get_ylim()[1] * 0.95,
                    f"{row['pod']} Running",
                    color="green",
                    fontsize=8,
                    rotation=90,
                    verticalalignment="top",
                )
            except KeyError:
                pass

    def plot_kafka_metric_with_cpu(
        ax, metric_df, cpu_df, title, ylabel, restarts_df, color_map
    ):
        for pod, pod_df in metric_df.groupby("pod"):
            ax.plot(
                pod_df["timestamp"],
                pod_df["rate_smoothed"],
                label=pod,
                color=color_map.get(pod),
                alpha=0.7,
            )
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True)

        # CPU overlay
        ax_right = ax.twinx()
        for pod, pod_df in cpu_df.groupby("pod"):
            ax_right.plot(
                pod_df["timestamp"],
                pod_df["cpu_percent_smoothed"],
                linestyle="--",
                label=f"{pod} CPU",
                color=color_map.get(pod, "gray"),
                alpha=0.4,
            )
        ax_right.set_ylabel("CPU %")

        # Restart annotations
        annotate_kafka_restarts(ax, restarts_df)

        annotate_spark_starts(
            ax,
            metric_df,
            df_status,
            top_offset=0.15,
            top_offset_inc=0.1,
            label_offset_secs=10,
        )

        return ax, ax_right

    # === Preprocess input metrics ===
    df_bytes_in = aggregate_and_process(
        kafka_bytes_in[kafka_bytes_in["topic"] == "control_power-avro"]
    )
    df_bytes_out = aggregate_and_process(
        kafka_bytes_out[kafka_bytes_out["topic"] == "control_power-avro"]
    )
    df_requests = aggregate_and_process(kafka_requests)
    df_errors = aggregate_and_process(kafka_requests_errors)
    df_messages_in = process_rate(
        kafka_messages_in[kafka_messages_in["topic"] == "control_power-avro"]
    )

    # === CPU usage ===
    cpu_df = df_cpu.sort_values(by=["pod", "timestamp"]).dropna(subset=["container"])
    cpu_df["value_diff"] = cpu_df.groupby("id")["value"].diff()
    cpu_df["time_diff"] = cpu_df.groupby("id")["timestamp"].diff().dt.total_seconds()
    cpu_df = cpu_df[(cpu_df["value_diff"] > 0) & (cpu_df["time_diff"] > 0)].copy()
    cpu_df["rate"] = (cpu_df["value_diff"] / cpu_df["time_diff"]) * 100
    cpu_df["cpu_percent_smoothed"] = cpu_df.groupby("pod")["rate"].transform(
        lambda x: x.rolling(window=3, min_periods=1).mean()
    )
    kafka_cpu_df = cpu_df[
        cpu_df["pod"].str.contains("streaming-kafka", case=False)
        | cpu_df["pod"].str.contains("master-kafka", case=False)
    ]
    kafka_cpu_df = kafka_cpu_df[kafka_cpu_df["container"] == "kafka"]

    # === Pod restarts ===

    def detect_pod_restart_and_running(df_kube_pod_status_phase):
        df = df_kube_pod_status_phase
        df = df[
            df["pod"].str.startswith("streaming-kafka")
            | df["pod"].str.startswith("labfaber-zookeeper")
            | df["pod"].str.startswith("master-kafka")
            | df["pod"].str.startswith("master-zookeeper")
        ]
        df = df[df["value"] == 1.0]
        df = df.sort_values(["pod", "timestamp"])

        restart_records = []

        for pod, pod_df in df.groupby("pod"):
            pod_df = pod_df.reset_index(drop=True)
            for i in range(1, len(pod_df)):
                prev_row = pod_df.iloc[i - 1]
                curr_row = pod_df.iloc[i]

                if prev_row["phase"] != "Pending" and curr_row["phase"] == "Pending":
                    # Start of a restart
                    restart_time = curr_row["timestamp"]

                    # Find next running status
                    running_rows = pod_df[
                        (pod_df["timestamp"] > restart_time)
                        & (pod_df["phase"] == "Running")
                    ]
                    if not running_rows.empty:
                        running_time = running_rows.iloc[0]["timestamp"]
                    else:
                        running_time = None

                    restart_records.append(
                        {
                            "pod": pod,
                            "restart_time": restart_time,
                            "running_time": running_time,
                        }
                    )

        return pd.DataFrame(restart_records)

    restarts_df = detect_pod_restart_and_running(df_status)

    # === Color map ===
    all_pods = sorted(
        set(df_requests["pod"].unique())
        | set(df_errors["pod"].unique())
        | set(df_bytes_in["pod"].unique())
        | set(df_bytes_out["pod"].unique())
    )
    palette = plt.get_cmap("tab20")
    colors = [palette(i % palette.N) for i in range(len(all_pods))]
    color_map = dict(zip(all_pods, colors))

    # === Plotting ===
    fig, axes = plt.subplots(4, 1, figsize=(18, 20), sharex=False)

    plot_kafka_metric_with_cpu(
        axes[0],
        df_requests,
        kafka_cpu_df,
        "Kafka Total Requests/sec per Broker",
        "Requests/sec",
        restarts_df,
        color_map,
    )

    plot_kafka_metric_with_cpu(
        axes[1],
        df_errors,
        kafka_cpu_df,
        "Kafka Request Errors/sec per Broker",
        "Errors/sec",
        restarts_df,
        color_map,
    )

    plot_kafka_metric_with_cpu(
        axes[2],
        df_bytes_in,
        kafka_cpu_df,
        "Kafka Incoming Traffic (KiB/sec)",
        "KiB/sec",
        restarts_df,
        color_map,
    )

    plot_kafka_metric_with_cpu(
        axes[3],
        df_bytes_out,
        kafka_cpu_df,
        "Kafka Outgoing Traffic (KiB/sec)",
        "KiB/sec",
        restarts_df,
        color_map,
    )

    fig.suptitle(title, fontsize=24)
    axes[-1].set_xlabel("Time")
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=local_tz))

    axes[0].legend(loc="upper right", fontsize="x-small", title="Kafka Pods")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def latency_box_plot(
    df_cloud: pd.DataFrame,
    df_edge: pd.DataFrame,
    y: str = "source_kafka_latency",
    title: str = "Distribution of Kafka Ingestion Latency (Cloud vs Edge)",
    save_path: str = None,
):
    # Custom colors for each category
    custom_palette = {
        "Edge": "#1f77b4",  # blue
        "Cloud": "#ff7f0e",  # orange
    }

    dfs_to_concat = []

    # 2. Prepare Edge DataFrame if not empty
    if not df_edge.empty:
        if y in df_edge.columns:
            df_edge_box = df_edge[[y]].copy()
            df_edge_box["Environment"] = "Edge"
            dfs_to_concat.append(df_edge_box)

    # 1. Prepare Cloud DataFrame if not empty
    if not df_cloud.empty:
        if y in df_cloud.columns:
            df_cloud_box = df_cloud[[y]].copy()
            df_cloud_box["Environment"] = "Cloud"
            dfs_to_concat.append(df_cloud_box)

    # 3. Concatenate if we have data
    if not dfs_to_concat:
        print("⚠️ Both DataFrames are empty. Nothing to plot.")
        return

    df_boxplot = pd.concat(dfs_to_concat, ignore_index=True)

    # 4. Plot with Seaborn
    plt.figure(figsize=(8, 6))
    ax = sns.boxplot(
        data=df_boxplot,
        x="Environment",
        y=y,
        hue="Environment",
        palette=custom_palette,
    )
    plt.title(title, fontsize=14, fontweight="bold")
    plt.ylabel("Latency (seconds)", fontsize=14)
    plt.xlabel("Environment", fontsize=14)
    plt.xticks(fontsize=14)
    plt.yticks(fontsize=14)

    if ax.get_legend():
        plt.setp(ax.get_legend().get_texts(), fontsize="14")
        plt.setp(ax.get_legend().get_title(), fontsize="14")

    plt.grid(True, axis="y", linestyle="--", alpha=0.7)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def _downsample_for_plot(df: pd.DataFrame, x: str, y: str, rule: str) -> pd.DataFrame:
    """Downsamples the DataFrame for plotting by aggregating data over time intervals.

    Preserves outliers by keeping min, mean, and max for each interval.

    Args:
        df: The input DataFrame containing the data to be downsampled.
        x: The name of the column containing timestamp data.
        y: The name of the column containing the values to be aggregated.
        rule: The offset string or object representing target conversion (e.g., '1s', '1min').

    Returns:
        A new DataFrame with downsampled data containing min, mean, and max values
        for each interval, sorted by the timestamp column.
    """
    if df.empty or not rule:
        return df

    # Ensure x is datetime for resampling
    if not pd.api.types.is_datetime64_any_dtype(df[x]):
        try:
            df = df.copy()
            df[x] = pd.to_datetime(df[x])
        except Exception:
            return df  # Cannot resample non-datetime

    # Resample and calculate min, mean, max
    # We aggregate y by the rule on x
    resampled = df.set_index(x)[[y]].resample(rule).agg(["min", "mean", "max"])

    # Drop intervals with no data
    resampled = resampled.dropna()

    # Flatten the result: we want rows for min, mean, and max
    # The columns are currently a MultiIndex: (y, 'min'), (y, 'mean'), (y, 'max')
    # We will extract each and concatenate them.

    dfs = []
    for stat in ["min", "mean", "max"]:
        temp = resampled[(y, stat)].reset_index()
        temp.columns = [x, y]
        dfs.append(temp)

    downsampled = pd.concat(dfs, ignore_index=True)
    downsampled = downsampled.sort_values(by=x)

    return downsampled


def latency_line_plot(
    df_cloud: pd.DataFrame,
    df_edge: pd.DataFrame,
    x: str = "source_timestamp",
    y: str = "source_kafka_latency",
    title: str = "Latency from Source to Kafka Broker (Cloud vs Edge)",
    linestyle: str = "none",
    save_path: str = None,
    downsample_rule: str = None,
):
    if df_cloud.empty and df_edge.empty:
        print("⚠️ All DataFrames are empty. Nothing to plot.")
        return

    # Apply downsampling if requested
    if downsample_rule:
        if not df_cloud.empty:
            df_cloud = _downsample_for_plot(df_cloud, x, y, downsample_rule)
        if not df_edge.empty:
            df_edge = _downsample_for_plot(df_edge, x, y, downsample_rule)

    plt.figure(figsize=(12, 6))

    if not df_cloud.empty:
        plt.plot(
            df_cloud[x],
            df_cloud[y],
            label="Cloud",
            marker="o",
            linestyle=linestyle,
            markersize=1,
        )

    if not df_edge.empty:
        plt.plot(
            df_edge[x],
            df_edge[y],
            label="Edge",
            marker="o",
            linestyle=linestyle,
            markersize=1,
        )

    plt.xlabel("Source Timestamp")
    plt.ylabel("Latency (Seconds)")
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def latency_distribution_plot(
    df_cloud: pd.DataFrame,
    df_edge: pd.DataFrame,
    x: str = "source_kafka_latency",
    title: str = "Latency Density of Kafka Ingestion (Cloud vs Edge)",
    save_path: str = None,
):
    dfs_to_concat = []

    if not df_cloud.empty:
        if x in df_cloud.columns:
            df_cloud_kde = df_cloud[[x]].copy()
            df_cloud_kde["Environment"] = "Cloud"
            dfs_to_concat.append(df_cloud_kde)

    if not df_edge.empty:
        if x in df_edge.columns:
            df_edge_kde = df_edge[[x]].copy()
            df_edge_kde["Environment"] = "Edge"
            dfs_to_concat.append(df_edge_kde)

    if not dfs_to_concat:
        print("⚠️ All DataFrames are empty. Nothing to plot.")
        return

    df_kde = pd.concat(dfs_to_concat, ignore_index=True)

    stats = df_kde.groupby("Environment")[x].agg(
        ["min", "max", "mean", "median", "std"]
    )
    print("📊 Statistics:")
    print(stats)

    # Custom colors for each category
    custom_palette = {
        "Edge": "#1f77b4",  # blue
        "Cloud": "#ff7f0e",  # orange
    }

    plt.figure(figsize=(10, 6))
    ax = sns.kdeplot(
        data=df_kde,
        x=x,
        hue="Environment",
        fill=True,
        common_norm=False,
        alpha=0.4,
        clip=(0, None),  # Trunca a estimativa no zero
        linewidth=1.5,
        palette=custom_palette,
    )

    plt.title(title, fontsize=14, fontweight="bold")
    plt.xlabel("Latency", fontsize=14)
    plt.ylabel("Density", fontsize=14)
    plt.yticks(fontsize=14)

    if ax.get_legend():
        plt.setp(ax.get_legend().get_texts(), fontsize="14")
        plt.setp(ax.get_legend().get_title(), fontsize="14")

    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def plot_spark_eventlog_charts(
    df_jobs: pd.DataFrame, df_stages: pd.DataFrame
) -> pd.DataFrame:
    sns.set_theme(style="whitegrid")

    # Heatmap of Job Durations over Time
    plt.figure(figsize=(14, 6))
    if "SubmissionTime" in df_jobs.columns:
        df_jobs["SubmissionTime_dt"] = pd.to_datetime(
            df_jobs["SubmissionTime"], unit="ms", utc=True
        ).dt.tz_convert("America/Sao_Paulo")
        df_jobs_sorted = df_jobs.sort_values(by="SubmissionTime_dt")
        plt.plot(
            df_jobs_sorted["SubmissionTime_dt"],
            df_jobs_sorted["DurationSec"],
            marker="o",
            linestyle="-",
        )
        plt.title("Job Duration Over Submission Time")
        plt.xlabel("Submission Time")
        plt.ylabel("Duration (seconds)")
        plt.xticks(rotation=45)
        plt.grid(True)
        plt.show()

    # KDE Plot (Density) of Stage Durations
    plt.figure(figsize=(12, 6))
    sns.kdeplot(df_stages["DurationSec"], shade=True, color="purple")
    plt.title("Density Plot of Stage Durations")
    plt.xlabel("Duration (seconds)")
    plt.ylabel("Density")
    plt.grid(True)
    plt.show()

    # Bonus: Histogram of Stage Durations
    plt.figure(figsize=(12, 6))
    sns.histplot(df_stages["DurationSec"], bins=50, kde=False, color="orange")
    plt.title("Histogram of Stage Durations")
    plt.xlabel("Duration (seconds)")
    plt.ylabel("Count")
    plt.grid(True)
    plt.show()

    # Intelligent mapping using modulo
    def map_job_type(job_id):
        job_type_mapping = {
            0: "Planning",  # Job 1
            1: "Kafka Fetch",  # Job 2
            2: "Transformations",  # Job 3
            3: "Sink Write",  # Job 4
        }
        return job_type_mapping.get(job_id % 3, "Unknown Job")

    # Apply mapping
    df_jobs["JobType"] = df_jobs["JobID"].apply(map_job_type)

    # If df_stages also has JobID (if not, we would need to fix differently)
    if "JobID" in df_stages.columns:
        df_stages["JobType"] = df_stages["JobID"].apply(map_job_type)
    else:
        df_stages["JobType"] = "Unknown Job"

    # --- Plot 1: Stage Duration vs Stage ID (colored by JobType) ---
    plt.figure(figsize=(12, 6))
    sns.scatterplot(
        x="StageID",
        y="DurationSec",
        hue="JobType",
        palette="tab10",
        data=df_stages,
        legend="full",
    )
    plt.title("Stage Duration vs Stage ID (Colored by Job Type)")
    plt.xlabel("Stage ID")
    plt.ylabel("Duration (seconds)")
    plt.axhline(
        df_stages["DurationSec"].mean(),
        color="red",
        linestyle="--",
        label="Mean Duration",
    )
    plt.legend(bbox_to_anchor=(1.05, 1), loc=2)
    plt.show()

    # --- Plot 2: Job Duration vs Job ID (colored by JobType) ---
    plt.figure(figsize=(12, 6))
    sns.scatterplot(
        x="JobID",
        y="DurationSec",
        hue="JobType",
        palette="tab10",
        data=df_jobs,
        legend="full",
    )
    plt.title("Job Duration vs Job ID (Colored by Job Type)")
    plt.xlabel("Job ID")
    plt.ylabel("Duration (seconds)")
    plt.axhline(
        df_jobs["DurationSec"].mean(),
        color="red",
        linestyle="--",
        label="Mean Duration",
    )
    plt.legend(bbox_to_anchor=(1.05, 1), loc=2)
    plt.show()

    # --- Plot 3: Stage Duration vs Number of Tasks (colored by JobType) ---
    plt.figure(figsize=(12, 6))
    sns.scatterplot(
        x="NumTasks",
        y="DurationSec",
        hue="JobType",
        palette="tab10",
        data=df_stages,
        legend="full",
    )
    plt.title("Stage Duration vs Number of Tasks (Colored by Job Type)")
    plt.xlabel("Number of Tasks")
    plt.ylabel("Duration (seconds)")
    plt.axhline(
        df_stages["DurationSec"].mean(),
        color="red",
        linestyle="--",
        label="Mean Duration",
    )
    plt.legend(bbox_to_anchor=(1.05, 1), loc=2)
    plt.show()

    return df_jobs


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

_CLOUD = "#1f77b4"  # blue
_EDGE = "#ff7f0e"  # orange


def _prepare_latency_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reshape a wide dataframe with latency columns into long form with
    columns: ['environment', 'stage', 'latency_s'].

    Required columns:
      - environment
      - source_kafka_latency  → stage 'Kafka'
      - kafka_landing_latency → stage 'Spark' (persistence)
      - total_latency         → stage 'Total'
    """
    required = {
        "environment",
        "source_kafka_latency",
        "kafka_landing_latency",
        "total_latency",
    }
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")

    long_df = df.melt(
        id_vars=["environment"],
        value_vars=[
            "source_kafka_latency",
            "kafka_landing_latency",
            "total_latency",
        ],
        var_name="metric",
        value_name="latency_s",
    )
    stage_map = {
        "source_kafka_latency": "Kafka",
        "kafka_landing_latency": "Spark",
        "total_latency": "Total",
    }
    long_df["stage"] = pd.Categorical(
        long_df["metric"].map(stage_map),
        categories=["Kafka", "Spark", "Total"],
        ordered=True,
    )
    return long_df.drop(columns=["metric"])


# --------------------------------------------------------------------
# 1) Grouped bar chart (Edge=orange, Cloud=blue; tones for median vs P95)
# --------------------------------------------------------------------
def latency_summary_bar_chart(df, save_path: str | None = None):
    """
    Creates a single figure with two subplots:
    - Left: Kafka latency summary
    - Right: Spark + Total latency summary
    """
    if df.empty:
        print("⚠️ DataFrame is empty. Nothing to plot.")
        return

    long_df = _prepare_latency_long(df)

    # Compute summary statistics
    summary = (
        long_df.groupby(["stage", "environment"])["latency_s"]
        .agg(median="median", p95=lambda s: np.percentile(s, 95))
        .reset_index()
    )

    # Define subsets
    stages_kafka = ["Kafka"]
    stages_other = ["Spark", "Total"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)

    def _plot(ax, stages, title):
        med = summary.pivot(
            index="stage", columns="environment", values="median"
        ).reindex(stages)
        p95 = summary.pivot(index="stage", columns="environment", values="p95").reindex(
            stages
        )

        x = np.arange(len(stages))
        w = 0.18
        gap = 0.22

        # Helper to safely get data
        def get_data(df_pivot, col):
            if col in df_pivot:
                return df_pivot[col].fillna(0)
            return np.zeros(len(stages))

        # Edge bars
        ax.bar(
            x - gap,
            get_data(med, "Edge"),
            width=w,
            label="Edge Median",
            color=_EDGE,
            alpha=0.55,
        )
        ax.bar(
            x - gap + w,
            get_data(p95, "Edge"),
            width=w,
            label="Edge 95th",
            color=_EDGE,
            alpha=1.0,
        )
        # Cloud bars
        ax.bar(
            x + gap,
            get_data(med, "Cloud"),
            width=w,
            label="Cloud Median",
            color=_CLOUD,
            alpha=0.55,
        )
        ax.bar(
            x + gap + w,
            get_data(p95, "Cloud"),
            width=w,
            label="Cloud 95th",
            color=_CLOUD,
            alpha=1.0,
        )

        ax.set_xticks(x + w / 2)
        ax.set_xticklabels(stages)
        ax.set_ylabel("Latency (seconds)")
        ax.set_title(title)
        ax.grid(True, axis="y", linestyle="--", alpha=0.6)

    # Plot Kafka
    _plot(axes[0], stages_kafka, "Kafka Latency")
    # Plot Spark + Total
    _plot(axes[1], stages_other, "Spark and Total Latency")

    # Shared legend
    legend_patches = [
        Patch(facecolor=_EDGE, edgecolor="none", alpha=1.0, label="Edge 95th"),
        Patch(facecolor=_EDGE, edgecolor="none", alpha=0.55, label="Edge Median"),
        Patch(facecolor=_CLOUD, edgecolor="none", alpha=1.0, label="Cloud 95th"),
        Patch(
            facecolor=_CLOUD,
            edgecolor="none",
            alpha=0.55,
            label="Cloud Median",
        ),
    ]
    fig.legend(handles=legend_patches, ncols=4, loc="upper center", frameon=True)

    fig.tight_layout(rect=[0, 0, 1, 0.92])  # leave space for legend
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


# --------------------------------------------------------------------
# 2) Violin + box overlay with robust Y-limits (clip by percentile)
# --------------------------------------------------------------------


def latency_violin_box_overlay(
    df: pd.DataFrame,
    save_path: str | None = None,
    stages: list[str] | None = None,
    clip_percentile: float = 99.0,
):
    """
    Violin plots + boxplots for Kafka, Spark, Total comparing Cloud vs Edge.
    Uses robust y-limits per panel based on the given percentile to avoid
    extreme outliers making the axis unusable.

    Parameters
    ----------
    df : DataFrame with columns:
         ['environment', 'source_kafka_latency', 'kafka_landing_latency', 'total_latency']
    save_path : optional file path to save the figure
    stages : optional ordering subset (default: ["Kafka","Spark","Total"])
    clip_percentile : float in (0,100]; y-axis upper bound per panel is set to
                      max(Pclip_edge, Pclip_cloud) where Pclip = given percentile.
    """
    if df.empty:
        print("⚠️ DataFrame is empty. Nothing to plot.")
        return

    long_df = _prepare_latency_long(df)
    if stages is None:
        stages = ["Kafka", "Spark", "Total"]

    fig, axes = plt.subplots(1, len(stages), figsize=(14, 4), sharey=False)

    for ax, stage in zip(axes, stages):
        dat_edge = long_df[
            (long_df["stage"] == stage) & (long_df["environment"] == "Edge")
        ]["latency_s"].values
        dat_cloud = long_df[
            (long_df["stage"] == stage) & (long_df["environment"] == "Cloud")
        ]["latency_s"].values

        # Prepare data and positions for violin/boxplot, filtering out empty arrays
        violins_data = []
        violins_pos = []
        boxplot_colors = []  # To store colors for boxplot patches

        if len(dat_edge) > 0:
            violins_data.append(dat_edge)
            violins_pos.append(1)
            boxplot_colors.append(_EDGE)
        if len(dat_cloud) > 0:
            violins_data.append(dat_cloud)
            violins_pos.append(2)
            boxplot_colors.append(_CLOUD)

        if not violins_data:
            ax.set_title(stage)
            ax.set_xticks([1, 2])
            ax.set_xticklabels(["Edge", "Cloud"])
            ax.set_ylabel("Latency (seconds)")
            ax.grid(True, axis="y", linestyle=":", alpha=0.6)
            continue  # No data for this stage, move to next

        parts = ax.violinplot(
            violins_data,
            showmeans=False,
            showmedians=False,
            showextrema=False,
            positions=violins_pos,
        )

        # Color violins
        bodies = parts["bodies"]
        for body, pos in zip(bodies, violins_pos):
            if pos == 1:  # Edge
                body.set_facecolor(_EDGE)
                body.set_edgecolor("black")
                body.set_alpha(0.25)
            elif pos == 2:  # Cloud
                body.set_facecolor(_CLOUD)
                body.set_edgecolor("black")
                body.set_alpha(0.25)

        # Boxplot overlay (colored medians)
        bp = ax.boxplot(
            violins_data,
            positions=violins_pos,
            widths=0.25,
            vert=True,
            showfliers=False,
            patch_artist=True,
            boxprops=dict(facecolor="white", edgecolor="black"),
            medianprops=dict(color="black", linewidth=1.5),
        )

        # Color the boxes' edges
        for patch, color in zip(bp["boxes"], boxplot_colors):
            patch.set_edgecolor(color)

        # Robust y-limit
        upper_limits = []
        if len(dat_edge) > 0:
            upper_limits.append(np.nanpercentile(dat_edge, clip_percentile))
        if len(dat_cloud) > 0:
            upper_limits.append(np.nanpercentile(dat_cloud, clip_percentile))

        if upper_limits:
            upper = max(upper_limits)
            if upper > 0:
                ax.set_ylim(0, upper * 1.1)
        else:
            ax.set_ylim(0, 1)  # Default small limit if no data

        ax.set_title(stage)
        ax.set_xticks([1, 2])
        ax.set_xticklabels(["Edge", "Cloud"])
        ax.set_ylabel("Latency (seconds)")
        ax.grid(True, axis="y", linestyle="--", alpha=0.6)

    fig.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


# Spark-only Gantt with Edge/Cloud subplots and warm-up highlighting
# Expected schema for each df_*:
#   columns=['timestamp','pod','phase','value', ...]
#     - timestamp: pandas.Timestamp (timezone-aware or naive)
#     - pod: string (full pod name)
#     - phase: string (e.g., 'Running', 'Pending', 'Succeeded', etc.)
#     - value: float (1.0 for active / selected rows, as in your existing code)
#
# Call:
#   spark_gantt_edge_cloud(df_edge, df_cloud, save_path="spark_gantt.png")
def spark_gantt_edge_cloud(
    df_edge: pd.DataFrame,
    df_cloud: pd.DataFrame,
    title: str = "Spark Pods Execution (Edge vs Cloud)",
    save_path: str | None = None,
    tz: str = "America/Sao_Paulo",
    phase_colors: dict | None = None,
    driver_patterns: list[str] = [
        r"driver$",
        r"streaming.*-driver$",
        r"^spark-.*-driver$",
    ],
    worker_patterns: list[str] = [r"-exec-\d+$", r"^spark-.*-exec-\d+$"],
    spark_prefixes: list[str] = [
        "deltalakewithminio",
        "streaming-pipeline-kafka-avro-to-delta-driver",
    ],
    dur_offset_pts: int = 20,  # horizontal text offset (points) from the center of the gold band; use negative to shift left
):
    local_tz = pytz.timezone(tz)

    if phase_colors is None:
        phase_colors = {
            "Running": "green",
            "Pending": "orange",
            "Failed": "red",
            "Succeeded": "blue",
            "Unknown": "gray",
        }

    def _starts_with_any(name: str, prefixes: list[str]) -> bool:
        return any(name.startswith(p) for p in prefixes)

    def _matches_any(name: str, patterns: list[str]) -> bool:
        return any(re.search(pat, name) for pat in patterns)

    def _only_spark(df: pd.DataFrame) -> pd.DataFrame:
        df = df[df["value"] == 1.0].copy()
        return df[df["pod"].apply(lambda p: _starts_with_any(p, spark_prefixes))]

    def _first_running_time(df: pd.DataFrame, pod_filter) -> pd.Timestamp | None:
        sub = df[(df["phase"] == "Running") & df["pod"].apply(pod_filter)]
        return pd.to_datetime(sub["timestamp"].min()) if not sub.empty else None

    def _latest_first_running_executor(
        df: pd.DataFrame,
    ) -> pd.Timestamp | None:
        exe = df[
            (df["phase"] == "Running")
            & df["pod"].apply(lambda p: _matches_any(p, worker_patterns))
        ]
        if exe.empty:
            return None
        firsts = exe.groupby("pod", as_index=False)["timestamp"].min()
        return pd.to_datetime(firsts["timestamp"].max())

    def _build_display_labels(df_env: pd.DataFrame) -> dict:
        pods = sorted(df_env["pod"].unique())
        driver = [p for p in pods if _matches_any(p, driver_patterns)]
        workers = [p for p in pods if _matches_any(p, worker_patterns)]
        others = [p for p in pods if p not in set(driver) | set(workers)]
        mapping = {}
        if driver:
            mapping[driver[0]] = "spark-driver"

        def _worker_key(x):
            m = re.search(r"(\d+)$", x)
            return int(m.group(1)) if m else x

        for i, w in enumerate(sorted(workers, key=_worker_key), start=1):
            mapping[w] = f"spark-worker-{i}"
        for o in others:
            mapping[o] = o
        return mapping

    def _fmt_td(td: pd.Timedelta) -> str:
        s = td.total_seconds()
        if s >= 3600:
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = s % 60
            return f"{h}h{m:02d}m{sec:04.1f}s"
        if s >= 60:
            m = int(s // 60)
            sec = s % 60
            return f"{m}m{sec:04.1f}s"
        return f"{s:.1f}s"

    def _fmt_clock(ts: pd.Timestamp) -> str:
        t = pd.to_datetime(ts)
        if t.tzinfo is None:
            t = local_tz.localize(t)
        else:
            t = t.tz_convert(local_tz)
        return t.strftime("%Hh%Mm%Ss")

    def _plot_env(ax, df_env: pd.DataFrame, panel_title: str):
        df_env = _only_spark(df_env).sort_values(["pod", "timestamp"]).copy()
        if df_env.empty:
            ax.set_title(panel_title + " (no data)")
            ax.set_axis_off()
            return

        warm_start = _first_running_time(
            df_env, lambda p: _matches_any(p, driver_patterns)
        )
        warm_end = _latest_first_running_executor(df_env)

        label_map = _build_display_labels(df_env)
        y_pods = sorted(df_env["pod"].unique(), key=lambda p: label_map.get(p, p))
        pod_to_y = {pod: i for i, pod in enumerate(y_pods)}

        seen = set()
        for pod in y_pods:
            sub = df_env[df_env["pod"] == pod].copy()
            sub["phase_shift"] = (sub["phase"] != sub["phase"].shift()).cumsum()
            for _, seg in sub.groupby("phase_shift"):
                phase = seg["phase"].iloc[0]
                label = phase if phase not in seen else None
                seen.add(phase)
                ax.hlines(
                    y=pod_to_y[pod],
                    xmin=seg["timestamp"].iloc[0],
                    xmax=seg["timestamp"].iloc[-1],
                    colors=phase_colors.get(phase, "black"),
                    linewidth=6,
                    label=label,
                )

        # Gold band with duration text; text is horizontally offset from the true center by dur_offset_pts
        if (
            (warm_start is not None)
            and (warm_end is not None)
            and (warm_end > warm_start)
        ):
            ax.axvspan(warm_start, warm_end, alpha=0.20, color="gold", label="Warm-up")
            dur = warm_end - warm_start
            mid_x = warm_start + dur / 2
            trans = mtransforms.blended_transform_factory(ax.transData, ax.transAxes)
            ax.text(
                mid_x,
                0.40,
                "Warmup Duration:\n" + _fmt_td(dur),
                transform=trans
                + mtransforms.ScaledTranslation(
                    dur_offset_pts / 72.0, 0, ax.figure.dpi_scale_trans
                ),
                ha="center",
                va="center",
                fontsize=9,
                color="black",
                zorder=5,
            )
        elif warm_start is not None:
            ax.axvline(
                warm_start,
                color="gold",
                linestyle="--",
                linewidth=2,
                label="Driver start",
            )

        # Driver start time printed right below the driver's line
        driver_pods = [p for p in y_pods if _matches_any(p, driver_patterns)]
        if warm_start is not None and driver_pods:
            dpod = driver_pods[0]
            y = pod_to_y[dpod]
            ax.annotate(
                "Driver Start:" + _fmt_clock(warm_start),
                xy=(warm_start, y),
                xytext=(
                    30,
                    12,
                ),  # move a bit below the line; increase magnitude to go farther
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=9,
                color="black",
            )

        ax.set_yticks(list(pod_to_y.values()))
        ax.set_yticklabels([label_map[p] for p in y_pods])
        ax.set_title(panel_title)
        ax.set_ylabel("Pods")
        ax.grid(True, axis="x", alpha=0.4)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=local_tz))

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharey=True)
    _plot_env(axes[0], df_edge.copy(), "Edge")
    _plot_env(axes[1], df_cloud.copy(), "Cloud")

    fig.suptitle(title, fontsize=18, y=0.97)

    handles0, labels0 = axes[0].get_legend_handles_labels()
    handles1, labels1 = axes[1].get_legend_handles_labels()
    by_label = dict(zip(labels0 + labels1, handles0 + handles1))
    fig.legend(
        by_label.values(),
        by_label.keys(),
        ncols=min(5, len(by_label)),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        frameon=True,
    )

    axes[0].set_xlabel("Time")
    axes[1].set_xlabel("Time")
    fig.tight_layout(rect=[0.02, 0.06, 1, 0.92])

    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()


def node_resources_2x2(
    df_cpu: pd.DataFrame,
    df_mem: pd.DataFrame,
    *,
    time_freq: str = "40s",
    cpu_limit_pct: float = 400.0,
    mem_limit_gib: float = 16.0,
    title: str = "Edge vs Cloud — CPU and Memory by Node",
    save_path: str | None = None,
):
    """
    Build a 2x2 figure with:
      (0,0) CPU Edge    (0,1) CPU Cloud
      (1,0) Mem Edge    (1,1) Mem Cloud

    Expected columns:
      df_cpu: ['timestamp','id','pod','node','container','value','environment']
              where 'value' is cumulative CPU time (e.g., millicores-seconds or CPU seconds)
      df_mem: ['timestamp','id','pod','node','container','value','environment']
              where 'value' is memory in bytes

    Notes:
      - We treat 'environment' values as 'Edge' and 'Cloud'.
      - CPU is computed as a per-id derivative over time, smoothed and then
        aggregated per node; units are percent.
      - Memory is converted to GiB, smoothed, then aggregated per node.
    """

    # Define your desired timezone
    local_tz = pytz.timezone("America/Sao_Paulo")

    # ---------------- CPU preprocessing (per your code) ----------------
    def _cpu_per_node(df: pd.DataFrame) -> pd.DataFrame:
        cpu_df = (
            df.sort_values(["id", "pod", "timestamp"])
            .dropna(subset=["container"])
            .copy()
        )
        cpu_df["value_diff"] = cpu_df.groupby("id")["value"].diff()
        cpu_df["time_diff"] = (
            cpu_df.groupby("id")["timestamp"].diff().dt.total_seconds()
        )
        cpu_df = cpu_df[(cpu_df["value_diff"] > 0) & (cpu_df["time_diff"] > 0)].copy()
        cpu_df["rate"] = (cpu_df["value_diff"] / cpu_df["time_diff"]) * 100.0
        cpu_df["cpu_percent"] = cpu_df.groupby("pod")["rate"].transform(
            lambda x: x.rolling(window=3, min_periods=1).mean()
        )
        df_resampled = (
            cpu_df[["timestamp", "node", "pod", "cpu_percent"]]
            .set_index("timestamp")
            .groupby(["node", "pod"])
            .resample(time_freq)
            .mean(numeric_only=True)
            .reset_index()
        )
        node_total = (
            df_resampled.groupby(["timestamp", "node"])["cpu_percent"]
            .sum()
            .unstack("node")
            .sort_index()
            .fillna(0.0)
        )
        return node_total

    # ---------------- Memory preprocessing (per your code) ----------------
    def _mem_per_node(df: pd.DataFrame) -> pd.DataFrame:
        mem_df = (
            df.sort_values(["timestamp", "pod"]).dropna(subset=["container"]).copy()
        )
        mem_df["memory_gib"] = mem_df["value"] / (1024.0**3)
        mem_df["memory_gib_smoothed"] = mem_df.groupby("pod")["memory_gib"].transform(
            lambda x: x.rolling(window=3, min_periods=1).mean()
        )
        mem_resampled = (
            mem_df[["timestamp", "node", "pod", "id", "memory_gib_smoothed"]]
            .set_index("timestamp")
            .groupby(["node", "pod", "id"])
            .resample(time_freq)
            .mean(numeric_only=True)
            .reset_index()
        )
        node_total = (
            mem_resampled.groupby(["timestamp", "node"])["memory_gib_smoothed"]
            .sum()
            .unstack("node")
            .sort_index()
            .fillna(0.0)
        )
        return node_total

    # Split by environment
    cpu_edge = _cpu_per_node(df_cpu[df_cpu["environment"] == "Edge"])
    cpu_cloud = _cpu_per_node(df_cpu[df_cpu["environment"] == "Cloud"])
    mem_edge = _mem_per_node(df_mem[df_mem["environment"] == "Edge"])
    mem_cloud = _mem_per_node(df_mem[df_mem["environment"] == "Cloud"])

    # ---------------- Plotting ----------------
    fig, axes = plt.subplots(2, 2, figsize=(16, 9), sharex=False)
    (ax_ce, ax_cc), (ax_me, ax_mc) = axes

    def _plot_lines(ax, frame: pd.DataFrame, ylabel: str, title: str):
        for node in frame.columns if frame is not None else []:
            ax.plot(frame.index, frame[node], label=str(node), linewidth=1.8)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.4, linestyle="--")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=local_tz))
        if frame.shape[1] <= 10:
            ax.legend(title="Node", loc="upper left", fontsize=9)

    # CPU: add y=cpu_limit_pct reference
    _plot_lines(ax_ce, cpu_edge, "CPU Usage (%)", "CPU — Edge")
    ax_ce.axhline(
        cpu_limit_pct,
        color="red",
        linestyle="--",
        linewidth=1.2,
        label=f"Limit {cpu_limit_pct:.0f}%",
    )
    _plot_lines(ax_cc, cpu_cloud, "CPU Usage (%)", "CPU — Cloud")
    ax_cc.axhline(
        cpu_limit_pct,
        color="red",
        linestyle="--",
        linewidth=1.2,
        label=f"Limit {cpu_limit_pct:.0f}%",
    )

    # Memory: add y=mem_limit_gib reference
    _plot_lines(ax_me, mem_edge, "Memory Usage (GiB)", "Memory — Edge")
    ax_me.axhline(
        mem_limit_gib,
        color="purple",
        linestyle="--",
        linewidth=1.2,
        label=f"Limit {mem_limit_gib:.0f} GiB",
    )
    _plot_lines(ax_mc, mem_cloud, "Memory Usage (GiB)", "Memory — Cloud")
    ax_mc.axhline(
        mem_limit_gib,
        color="purple",
        linestyle="--",
        linewidth=1.2,
        label=f"Limit {mem_limit_gib:.0f} GiB",
    )

    # X labels only on bottom row
    ax_me.set_xlabel("Time")
    ax_mc.set_xlabel("Time")

    fig.suptitle(title, fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    if save_path:
        plt.savefig(save_path, dpi=400, bbox_inches="tight")
    plt.show()
