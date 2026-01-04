#!/bin/bash
set -euo pipefail

# Default values
DURATION="60s"
INTERVAL="1"
OUTPUT_FILE="resources.csv"

# Function to display help
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  --duration DURATION  Duration of recording (e.g., 60s, 10m). Default: 60s"
    echo "  --interval INTERVAL  Interval between updates in seconds. Default: 1"
    echo "  --output FILE        Output CSV file. Default: resources.csv"
    echo "  --help               Display this help message"
    exit 1
}

# Parse named arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --duration) DURATION="$2"; shift ;;
        --interval) INTERVAL="$2"; shift ;;
        --output) OUTPUT_FILE="$2"; shift ;;
        --help) usage ;;
        *) echo "Unknown parameter passed: $1"; usage ;;
    esac
    shift
done

# Check if vmstat is installed
if ! command -v vmstat &> /dev/null; then
    echo "Error: vmstat is not installed. Please install it (usually in procps package)."
    exit 1
fi

echo "Starting resource monitoring (vmstat)..."
echo "Duration: $DURATION"
echo "Interval: $INTERVAL"
echo "Output: $OUTPUT_FILE"

# Convert duration to seconds for vmstat count calculation
if [[ "$DURATION" =~ ([0-9]+)([a-zA-Z]*) ]]; then
    VALUE="${BASH_REMATCH[1]}"
    UNIT="${BASH_REMATCH[2]}"
    case "$UNIT" in
        s|"") SECONDS=$VALUE ;;
        m) SECONDS=$((VALUE * 60)) ;;
        h) SECONDS=$((VALUE * 3600)) ;;
        *) echo "Unknown duration unit: $UNIT"; exit 1 ;;
    esac
else
    echo "Invalid duration format: $DURATION"
    exit 1
fi

COUNT=$((SECONDS / INTERVAL))

# Capture Total Memory in KB for percentage calculation
if command -v free &> /dev/null; then
    # free -k output:
    #               total        used        free      shared  buff/cache   available
    # Mem:       16303868     8463860     2543360      367468     5296648     7084660
    # We want the second column of the line starting with Mem:
    TOTAL_MEM_KB=$(free -k | grep "^Mem:" | awk '{print $2}')
else
    echo "Warning: 'free' command not found. Memory percentage calculation might be inaccurate."
    TOTAL_MEM_KB="0"
fi

# Write Metadata Header
echo "# TOTAL_MEM_KB: $TOTAL_MEM_KB" > "$OUTPUT_FILE"

# Run vmstat
# -t: Add timestamp
# -n: One header
# -w: Wide output (if available, better for high memory) -> Optional, keeping simple for now.
# We assume standard vmstat output structure.
# Custom formatting to CSV via awk.

# vmstat -t -n 1 5 output looks like:
# procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu----- -----timestamp-----
#  r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st                 UTC
#  0  0      0 7654320  1234  567890    0    0     0     0   10   20  1  0 99  0  0 2026-01-04 15:30:00

# We need to skip the first line ("procs ..."), take the second as header, and data.
# The timestamp is the last two fields (Date Time).

vmstat -t -n "$INTERVAL" "$COUNT" | awk -v OFS=, '
NR==1 {next}
NR==2 {
    header = "";
    for (i=1; i<=NF-1; i++) {
        header = header $i ",";
    }
    header = header "timestamp";
    print header;
    next;
}
{
    line = "";
    timestamp = $(NF-1) " " $NF;
    for (i=1; i<=NF-2; i++) {
        line = line $i ",";
    }
    line = line timestamp;
    print line;
}' >> "$OUTPUT_FILE"

echo "Data saved to $OUTPUT_FILE"
