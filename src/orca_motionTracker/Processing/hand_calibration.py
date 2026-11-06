import json
import numpy as np

from pathlib import Path

from orca_motionTracker.Processing.finger_mapping import FINGERS

MIN_CALIBRATION_RANGE = 0.10

class HandCalibration:

    def __init__(self, calibration_file):

        self.calibration_file = Path(calibration_file)

        self.calibration = self.load_calibration()

        self.validate_calibration()

    def load_calibration(self):
        with open(self.calibration_file, "r") as file:
            data = json.load(file)

        return data["fingers"]

    def validate_calibration(self):
        for finger in FINGERS:

            if finger not in self.calibration:
                raise ValueError(f"Missing calibration for {finger}")\

        open_value = self.calibration[finger]["open"]
        closed_value = self.calibration[finger]["closed"]

        difference = closed_value - open_value

        if difference < MIN_CALIBRATION_RANGE:
            raise ValueError(
                f"Invalid calibration for {finger}: "
                f"open={open_value:.3f}, "
                f"closed={closed_value:.3f}, "
                f"difference={difference:.3f}. "
                f"Minimum required difference is: {MIN_CALIBRATION_RANGE}"
            )

    def normalize(self, raw_flexion):
        normalized = {}

        for finger in FINGERS:

            open_value = self.calibration[finger]["open"]
            closed_value = self.calibration[finger]["closed"]

            value = (raw_flexion[finger] - open_value) / (closed_value - open_value)

            normalized[finger] = float(np.clip(value, 0.0, 1.0))

        return normalized
    