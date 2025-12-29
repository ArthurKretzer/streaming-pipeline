import os
import argparse
from robot_dataset import RobotDataset
from common.logger import log

logger = log("ExportDataset")


def export_dataset(output_path: str, max_rows: int = None):
    """
    Exports the robot dataset to a Parquet file.

    Args:
        output_path: Path to save the parquet file
        max_rows: Optional limit on number of rows
    """
    logger.info(f"Loading dataset (max_rows={max_rows})...")
    # Using 'robot_data' to get the full dataset with all columns
    dataset_loader = RobotDataset(normalize=False, max_rows=max_rows)
    df = dataset_loader.get_dataset(data_type="robot_data")

    logger.info(f"Dataset loaded: {len(df)} rows. Saving to {output_path}...")

    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df.to_parquet(output_path, index=False)
    logger.info("Export completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export Robot Dataset to Parquet"
    )
    parser.add_argument(
        "--output",
        default="data/robot_data.parquet",
        help="Output path for parquet file",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=36000,
        help="Max rows to export (default 36000 for 1h @ 10Hz)",
    )

    args = parser.parse_args()

    export_dataset(args.output, args.max_rows)
