import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Union, Optional

import dotenv
import numpy as np

ValueType = Union[float, int]


@dataclass
class FromEnv:
    name: str
    default: Optional[str] = ""


class Datalogger(ABC):

    @abstractmethod
    def __enter__(self):
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @abstractmethod
    def log(self, measurement: str, value: ValueType, experiment: str, *, timestamp: np.datetime64 = None):
        pass

    @abstractmethod
    def query(
            self,
            time_from: np.datetime64,
            time_to: np.datetime64 = None,
            *,
            experiment: str
    ) -> np.ndarray:
        pass

    def pivot_measurements(self, data: np.ndarray) -> np.ndarray:
        times = np.unique(data["time"])
        measurements = np.unique(data["measurement"])

        dtype = [("time", "datetime64[ns]")] + [(m, "f8") for m in measurements]
        out = np.empty(len(times), dtype=dtype)
        out["time"] = times

        for m in measurements:
            mask = data["measurement"] == m
            lookup = dict(zip(data["time"][mask], data["value"][mask]))
            out[m] = [lookup.get(t, np.nan) for t in times]
        return out

    def get_config(self, value: str | FromEnv) -> str:
        dotenv.load_dotenv()
        if isinstance(value, FromEnv):
            return os.getenv(value.name, value.default)
        return value
