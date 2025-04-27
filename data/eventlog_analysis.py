import json

import pandas as pd


# Function to load event log file
def load_eventlog(filepath):
    events = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue  # skip empty lines
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON line: {line}")
                continue
    return events


# Function to extract jobs, stages, and tasks data
def extract_spark_events(events):
    jobs = []
    stages = []

    for event in events:
        if event["Event"] == "SparkListenerJobStart":
            jobs.append(
                {
                    "JobID": event["Job ID"],
                    "SubmissionTime": event.get("Submission Time"),
                }
            )
        elif event["Event"] == "SparkListenerJobEnd":
            for job in jobs:
                if job["JobID"] == event["Job ID"]:
                    job["CompletionTime"] = event.get("Completion Time")
                    job["JobResult"] = event["Job Result"]["Result"]
                    break
        elif event["Event"] == "SparkListenerStageCompleted":
            stage_info = event["Stage Info"]
            stages.append(
                {
                    "StageID": stage_info["Stage ID"],
                    "StageAttemptID": stage_info["Stage Attempt ID"],
                    "StageName": stage_info.get("Stage Name", "unknown"),
                    "SubmissionTime": stage_info.get("Submission Time"),
                    "CompletionTime": stage_info.get("Completion Time"),
                    "NumTasks": stage_info.get("Number of Tasks", 0),
                    "ShuffleReadBytes": stage_info.get("Shuffle Read Metrics", {}).get(
                        "Remote Bytes Read", 0
                    ),
                    "ShuffleWriteBytes": stage_info.get(
                        "Shuffle Write Metrics", {}
                    ).get("Shuffle Bytes Written", 0),
                    "InputRecords": next(
                        (
                            int(acc["Value"])
                            for acc in stage_info.get("Accumulables", [])
                            if acc["Name"] == "internal.metrics.input.recordsRead"
                        ),
                        0,
                    ),
                    "OutputRecords": next(
                        (
                            int(acc["Value"])
                            for acc in stage_info.get("Accumulables", [])
                            if acc["Name"] == "internal.metrics.output.recordsWritten"
                        ),
                        0,
                    ),
                    "GC Time (ms)": next(
                        (
                            int(acc["Value"])
                            for acc in stage_info.get("Accumulables", [])
                            if acc["Name"] == "internal.metrics.jvmGCTime"
                        ),
                        0,
                    ),
                    "Duration (ms)": next(
                        (
                            int(acc["Value"])
                            for acc in stage_info.get("Accumulables", [])
                            if acc["Name"] == "duration"
                        ),
                        0,
                    ),
                }
            )

    df_jobs = pd.DataFrame(jobs)
    df_stages = pd.DataFrame(stages)

    # Calculate durations
    if not df_jobs.empty:
        df_jobs["DurationSec"] = (
            df_jobs["CompletionTime"] - df_jobs["SubmissionTime"]
        ) / 1000
    if not df_stages.empty:
        df_stages["DurationSec"] = (
            df_stages["CompletionTime"] - df_stages["SubmissionTime"]
        ) / 1000

    return df_jobs, df_stages


# Function to summarize data
def summarize_jobs_stages(df_jobs, df_stages):
    print("\n=== Jobs Summary ===")
    print(df_jobs.describe())

    print("\n=== Stages Summary ===")
    print(df_stages.describe())

    print("\nTop 5 Slowest Stages:")
    print(df_stages.sort_values(by="DurationSec", ascending=False).head())

    print("\nTop 5 Stages by Shuffle Read:")
    if "ShuffleReadBytes" in df_stages.columns:
        print("\nTop 5 Stages by Shuffle Read:")
        print(df_stages.sort_values(by="ShuffleReadBytes", ascending=False).head())
    else:
        print("\nNo Shuffle Read data available in this log.")


# Example Usage
if __name__ == "__main__":
    eventlog_path = "./data/raw/first_experiment/eventLogs.json"  # <- Change this

    print("Reading Logs...")
    events = load_eventlog(eventlog_path)
    print("Done.")
    df_jobs, df_stages = extract_spark_events(events)
    summarize_jobs_stages(df_jobs, df_stages)
    df_jobs.to_parquet("./data/raw/df_jobs.parquet", index=False)
    df_stages.to_parquet("./data/raw/df_stages.parquet", index=False)
