import argparse
import pandas as pd
import matplotlib.pyplot as plt
import os
import re


def parse_arguments():
    parser = argparse.ArgumentParser(description="Analyze system resources from CSV.")
    parser.add_argument("--input", type=str, required=True, help="Input CSV file")
    return parser.parse_args()


def get_total_memory(file_path):
    """
    Reads the Total Memory metadata from the first line of the CSV.
    Format: # TOTAL_MEM_KB: 12345
    """
    total_mem = None
    with open(file_path, "r") as f:
        first_line = f.readline()
        match = re.search(r"# TOTAL_MEM_KB: (\d+)", first_line)
        if match:
            total_mem = int(match.group(1))
    return total_mem


def main():
    args = parse_arguments()
    input_file = args.input
    output_file = os.path.splitext(input_file)[0] + ".png"

    print(f"Analyzing {input_file}...")

    # Read Metadata
    total_mem_kb = get_total_memory(input_file)
    if total_mem_kb:
        print(f"Total Memory detected: {total_mem_kb} KB")
    else:
        print(
            "Warning: Total memory metadata not found. Memory percentage will be estimated or skipped."
        )

    # Read CSV, skipping comments
    try:
        df = pd.read_csv(input_file, comment="#", skipinitialspace=True)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # Process Timestamp
    # Combine Date + Time if split, but our awk script already puts them in the last column.
    # vmstat -t format: YYYY-MM-DD HH:MM:SS
    # Check if 'timestamp' column exists
    if "timestamp" in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"])
    else:
        # Fallback if manual column combination needed or if awk failed
        print("Error: 'timestamp' column not found.")
        return

    # Calculate CPU Usage (Total %)
    # vmstat: us (user), sy (system), id (idle), wa (wait), st (steal)
    # Total Usage = 100 - idle
    if "id" in df.columns:
        df["cpu_usage_percent"] = 100 - df["id"]
    else:
        print("Error: 'id' (idle CPU) column not found.")
        return

    # Calculate Memory Usage (%)
    # vmstat: free, buff, cache in KB
    # Used = Total - Free - Buff - Cache
    if total_mem_kb and {"free", "buff", "cache"}.issubset(df.columns):
        # Convert to int to be safe
        df["free"] = pd.to_numeric(df["free"])
        df["buff"] = pd.to_numeric(df["buff"])
        df["cache"] = pd.to_numeric(df["cache"])

        df["used_mem_kb"] = total_mem_kb - df["free"] - df["buff"] - df["cache"]
        df["mem_usage_percent"] = (df["used_mem_kb"] / total_mem_kb) * 100
    else:
        print(
            "Warning: Cannot calculate memory percentage (missing metadata or columns)."
        )
        df["mem_usage_percent"] = 0

    # Plotting
    plt.figure(figsize=(12, 6))

    # Plot CPU
    plt.plot(
        df["datetime"],
        df["cpu_usage_percent"],
        label="Total CPU Usage (%)",
        color="tab:blue",
        linewidth=1.5,
    )

    # Plot Memory
    if total_mem_kb:
        plt.plot(
            df["datetime"],
            df["mem_usage_percent"],
            label="Total Memory Usage (%)",
            color="tab:orange",
            linewidth=1.5,
        )

    plt.title(f"System Resource Usage: {os.path.basename(input_file)}")
    plt.xlabel("Time")
    plt.ylabel("Percentage (%)")
    plt.ylim(0, 105)
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    print(f"Saving chart to {output_file}...")
    plt.savefig(output_file)
    print("Done.")


if __name__ == "__main__":
    main()
