from typing import Self, List, Optional, Callable

import numpy as np
import sounddevice as sd
from scipy._lib._ccallback import CData

from workbench.instruments import Instrument


InputCallback = Callable[[np.ndarray, int, CData, sd.CallbackFlags], None]
OutputCallback = Callable[[np.ndarray, int, CData, sd.CallbackFlags], None]

class MOTOUltraLiteMk5(Instrument):

    def __init__(self, device_name: str, sample_rate: int):
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.stream = sd.Stream(
            device=self.device_name,
            samplerate=sample_rate or self.sample_rate,
            callback=self._callback)

    def _callback(self, in_data, out_data, frame_count, time_info, status_flags):
        out_data.fill(0)

    def __enter__(self):
        self.stream.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stream.stop()

    @classmethod
    def connect(cls, address: str = "UltraLite-mk5") -> Self:
        device_info = sd.query_devices(address)
        if device_info is None:
            raise IOError("Device not found")
        return cls(
            device_info["name"],
            sample_rate=device_info["default_samplerate"])


if __name__ == "__main__":
    with MOTOUltraLiteMk5.connect() as motu_ultralite_mk5:
        import time; time.sleep(4)