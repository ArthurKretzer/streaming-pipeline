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
    tasks = []

    job_stage_mapping = {}  # JobID -> list of StageIDs

    for event in events:
        if event["Event"] == "SparkListenerJobStart":
            job_id = event["Job ID"]
            stage_ids = [s["Stage ID"] for s in event.get("Stage Infos", [])]
            jobs.append(
                {
                    "JobID": job_id,
                    "SubmissionTime": event.get("Submission Time"),
                }
            )
            job_stage_mapping[job_id] = stage_ids

        elif event["Event"] == "SparkListenerJobEnd":
            job_id = event["Job ID"]
            for job in jobs:
                if job["JobID"] == job_id:
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

        elif event["Event"] == "SparkListenerTaskEnd":
            task_info = event["Task Info"]
            task_metrics = event.get("Task Metrics", {})
            tasks.append(
                {
                    "TaskID": task_info["Task ID"],
                    "StageID": event["Stage ID"],
                    "StageAttemptID": event["Stage Attempt ID"],
                    "ExecutorID": task_info.get("Executor ID"),
                    "Host": task_info.get("Host"),
                    "LaunchTime": task_info.get("Launch Time"),
                    "FinishTime": task_info.get("Finish Time"),
                    "Duration": task_info.get("Finish Time")
                    - task_info.get("Launch Time")
                    if task_info.get("Launch Time") and task_info.get("Finish Time")
                    else None,
                    "Successful": task_info.get("Successful"),
                    "BytesRead": task_metrics.get("InputMetrics", {}).get(
                        "Bytes Read", 0
                    ),
                    "ShuffleReadBytes": task_metrics.get(
                        "Shuffle Read Metrics", {}
                    ).get("Remote Bytes Read", 0),
                    "ShuffleWriteBytes": task_metrics.get(
                        "Shuffle Write Metrics", {}
                    ).get("Shuffle Bytes Written", 0),
                    "MemoryBytesSpilled": task_metrics.get("Memory Bytes Spilled", 0),
                    "DiskBytesSpilled": task_metrics.get("Disk Bytes Spilled", 0),
                    # Add more task metrics if you need
                }
            )

    df_jobs = pd.DataFrame(jobs)
    df_stages = pd.DataFrame(stages)
    df_tasks = pd.DataFrame(tasks)

    # --- Post Processing ---

    # Associate Stage -> Job
    if not df_stages.empty and not df_jobs.empty:
        stage_to_job = {}
        for job_id, stage_ids in job_stage_mapping.items():
            for stage_id in stage_ids:
                stage_to_job[stage_id] = job_id

        df_stages["JobID"] = df_stages["StageID"].map(stage_to_job)

    # Calculate durations
    if not df_jobs.empty:
        df_jobs["DurationSec"] = (
            df_jobs["CompletionTime"] - df_jobs["SubmissionTime"]
        ) / 1000
    if not df_stages.empty:
        df_stages["DurationSec"] = (
            df_stages["CompletionTime"] - df_stages["SubmissionTime"]
        ) / 1000
    if not df_tasks.empty:
        df_tasks["DurationSec"] = df_tasks["Duration"] / 1000

    return df_jobs, df_stages, df_tasks


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
    experiment_name = "fourth_experiment"

    eventlog_path = f"./data/raw/{experiment_name}/eventLogs.json"  # <- Change this

    print("Reading Logs...")
    events = load_eventlog(eventlog_path)
    print("Done.")
    df_jobs, df_stages, df_tasks = extract_spark_events(events)
    summarize_jobs_stages(df_jobs, df_stages)
    df_jobs.to_parquet(f"./data/raw/{experiment_name}/df_jobs.parquet", index=False)
    df_stages.to_parquet(f"./data/raw/{experiment_name}/df_stages.parquet", index=False)
    df_tasks.to_parquet(f"./data/raw/{experiment_name}/df_tasks.parquet", index=False)
