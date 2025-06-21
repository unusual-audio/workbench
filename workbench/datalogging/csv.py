import csv
from os import PathLike
from pathlib import Path

import numpy as np

from workbench.datalogging import Datalogger, ValueType


class CSVDataLogger(Datalogger):

    def __init__(self, filename: PathLike | str):
        self.filename = Path(filename)

    def __enter__(self):
        try:
            open(self.filename, "x").close()
        except FileExistsError:
            pass
        self.fp = open(self.filename, "a")
        self.writer = csv.DictWriter(self.fp, fieldnames=["time", "measurement", "value", "experiment"])
        if self.fp.tell() == 0:
            self.writer.writeheader()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fp.close()

    def log(self, measurement: str, value: ValueType, experiment: str, *, timestamp: np.datetime64 = None):
        self.writer.writerow({
            "time": timestamp or np.datetime64(datetime.now()),
            "measurement": measurement,
            "value": value,
            "experiment": experiment})
        self.fp.flush()

    def query(
            self,
            time_from: np.datetime64,
            time_to: np.datetime64 = None,
            *,
            experiment: str
    ) -> np.ndarray:
        time_to = time_to or np.datetime64("now") + np.timedelta64(1, "s")
        rows = []
        with self.filename.open("r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["experiment"] != experiment:
                    continue
                timestamp = np.datetime64(row["time"])
                if not (time_from <= timestamp <= time_to):
                    continue
                rows.append((timestamp, row["measurement"], float(row["value"])))

        dtype = [("time", "datetime64[ns]"), ("measurement", "U64"), ("value", "f8")]
        return self.pivot_measurements(np.array(rows, dtype=dtype))
