from typing import Union
from importlib.resources import files, as_file

import numpy as np
import pandas as pd

# Data from <https://www.fluke.com/en-us/learn/tools-calculators/pt100-table-generator>
with as_file(files("workbench") / "resources" / "pt100_3850.csv") as f:
    _df = pd.read_csv(f)  # PT-385, R₀ = 100 Ω, TCR = 3850 ppm/K
R = _df["Resistance (ohms)"].values
T = _df["Temperature (Celsius)"].values


def r_to_c(r: Union[float, np.float64, np.array], r0: float = 100.0) -> Union[np.float64, np.array]:
    return np.interp(np.asarray(r / (r0 / 100)), R, T)
