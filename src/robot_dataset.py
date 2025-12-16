import pandas as pd
from dotenv import load_dotenv
from RoADDataset import Dataset

from common.logger import log

logger = log("RobotDataset")
load_dotenv()


class RobotDataset:
    control_power_columns = [
        "robot_action_id",
        "apparent_power",
        "current",
        "frequency",
        "phase_angle",
        "power",
        "power_factor",
        "reactive_power",
        "voltage",
    ]

    accelerometer_gyro_columns = [
        "j01_x_acc",
        "j01_y_acc",
        "j01_z_acc",
        "j01_x_ang_velocity",
        "j01_y_ang_velocity",
        "j01_z_ang_velocity",
        "j01_01_quartenion_orientation",
        "j01_02_quartenion_orientation",
        "j01_03_quartenion_orientation",
        "j01_04_quartenion_orientation",
        "j01_temperature",
        "j02_x_acc",
        "j02_y_acc",
        "j02_z_acc",
        "j02_x_ang_velocity",
        "j02_y_ang_velocity",
        "j02_z_ang_velocity",
        "j02_01_quartenion_orientation",
        "j02_02_quartenion_orientation",
        "j02_03_quartenion_orientation",
        "j02_04_quartenion_orientation",
        "j02_temperature",
        "j03_x_acc",
        "j03_y_acc",
        "j03_z_acc",
        "j03_x_ang_velocity",
        "j03_y_ang_velocity",
        "j03_z_ang_velocity",
        "j03_01_quartenion_orientation",
        "j03_02_quartenion_orientation",
        "j03_03_quartenion_orientation",
        "j03_04_quartenion_orientation",
        "j03_temperature",
        "j04_x_acc",
        "j04_y_acc",
        "j04_z_acc",
        "j04_x_ang_velocity",
        "j04_y_ang_velocity",
        "j04_z_ang_velocity",
        "j04_01_quartenion_orientation",
        "j04_02_quartenion_orientation",
        "j04_03_quartenion_orientation",
        "j04_04_quartenion_orientation",
        "j04_temperature",
        "j05_x_acc",
        "j05_y_acc",
        "j05_z_acc",
        "j05_x_ang_velocity",
        "j05_y_ang_velocity",
        "j05_z_ang_velocity",
        "j05_01_quartenion_orientation",
        "j05_02_quartenion_orientation",
        "j05_03_quartenion_orientation",
        "j05_04_quartenion_orientation",
        "j05_temperature",
        "j06_x_acc",
        "j06_y_acc",
        "j06_z_acc",
        "j06_x_ang_velocity",
        "j06_y_ang_velocity",
        "j06_z_ang_velocity",
        "j06_01_quartenion_orientation",
        "j06_02_quartenion_orientation",
        "j06_03_quartenion_orientation",
        "j06_04_quartenion_orientation",
        "j06_temperature",
        "j07_x_acc",
        "j07_y_acc",
        "j07_z_acc",
        "j07_x_ang_velocity",
        "j07_y_ang_velocity",
        "j07_z_ang_velocity",
        "j07_01_quartenion_orientation",
        "j07_02_quartenion_orientation",
        "j07_03_quartenion_orientation",
        "j07_04_quartenion_orientation",
        "j07_temperature",
    ]

    def __init__(self, normalize: bool = False, max_rows: int = None):
        self.max_rows = max_rows
        self.columns = (
            self.control_power_columns + self.accelerometer_gyro_columns
        )
        dataset_raw = Dataset(normalize=normalize)
        training_subset = dataset_raw.sets["training"]
        self.dataset = self._concat_subsets(training_subset)

    def _concat_subsets(self, subsets: list) -> pd.DataFrame:
        """Concatenate subsets into a single DataFrame."""
        data_frames = []
        total_rows = 0
        for subset in subsets:
            df = pd.DataFrame(subset, columns=self.columns)
            data_frames.append(df)
            total_rows += len(df)
            if self.max_rows and total_rows >= self.max_rows:
                break

        if not data_frames:
            return pd.DataFrame(columns=self.columns)

        full_df = pd.concat(
            data_frames,
            ignore_index=True,
        )

        if self.max_rows:
            full_df = full_df.head(self.max_rows)

        return full_df

    def get_dataset(self, data_type: str) -> pd.DataFrame:
        if data_type == "control_power":
            return self._get_control_power_data()
        elif data_type == "accelerometer_gyro":
            return self._get_temperature_accelerometer_gyro_data()
        else:
            logger.error(f"Invalid data type ({data_type}) for producer.")
            raise ValueError(f"Invalid data type ({data_type}) for producer.")

    def _get_control_power_data(self) -> pd.DataFrame:
        return self.dataset[self.control_power_columns]

    def _get_temperature_accelerometer_gyro_data(self) -> pd.DataFrame:
        return self.dataset[self.accelerometer_gyro_columns]
