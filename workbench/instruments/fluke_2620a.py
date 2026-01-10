from __future__ import annotations

from datetime import datetime
from typing import Optional, Self

from serial import Serial

from workbench.instruments import Instrument


class Fluke2620A(Instrument):
    instrument_name = "Fluke 2620A"

    def __init__(self, address: str):
        self.device = Serial(address)

    def identity(self) -> str:
        return self.query("*IDN?")

    def reset(self):
        self.write("*RST")

    def vdc(self, channel: int, fixed_range: Optional[int] = None):
        """
        Configure a channel for DC voltage measurement.

        Manual ranges:
          1: 300 mV
          2: 3 V
          3: 30 V
          4: 300 V

        """
        self.write(f"FUNC {channel},VDC,{fixed_range or 'AUTO'}")

    def vac(self, channel: int, fixed_range: Optional[int] = None):
        """
        Configure a channel for AC voltage measurement.

        Manual ranges:
          1: 300 mV
          2: 3 V
          3: 30 V
          4: 300 V

        """
        self.write(f"FUNC {channel},VAC,{fixed_range or 'AUTO'}")

    def freq(self, channel: int, fixed_range: Optional[int] = None):
        """
        Configure a channel for frequency measurement.

        Manual ranges:
          1: 900 Hz
          2: 9 kHz
          3: 90 kHz
          4: 900 kHz
          5: 1 MHz

        """
        self.write(f"FUNC {channel},FREQ,{fixed_range or 'AUTO'}")

    def ohms(self, channel: int, fixed_range: Optional[int] = None, terminals: int = 2):
        """
        Configure a channel for frequency measurement.

        Manual ranges:
          1: 300 Ω
          2: 3 kΩ
          3: 30 kΩ
          4: 300 kΩ
          5: 3 MΩ
          6: 10 MΩ

        """
        self.write(f"FUNC {channel},OHMS,{fixed_range or 'AUTO'},{terminals}")

    def thermocouple(self, channel: int, thermocouple_type: str = "K"):
        self.write(f"FUNC {channel},TEMP,{thermocouple_type}")

    def rtd(self, channel: int, terminals: int = 2):
        self.write(f"FUNC {channel},TEMP,PT,{terminals}")

    def off(self, channel: int):
        self.write(f"FUNC {channel},OFF")

    def rate(self, rate: int):
        """
        Configure the measurement rate.

        Values:
          0: Slow
          1: Fast

        """
        self.write(f"RATE {rate}")

    def trigger(self):
        self.write("*TRG")

    def next_values(self) -> tuple[datetime, list[float], int, int, float]:
        r = self.query("NEXT?")
        h, m, s, mo, d, y, *values, alarms, dio, total = r.split(",")
        h, m, s = int(h), int(m), int(s)
        mo, d, y = int(mo), int(d), int(y) + 2000
        time = datetime(y, mo, d, h, m, s)
        values = [float(i) for i in values]
        alarms, dio = int(alarms), int(dio)
        total = float(total)
        return time, values, alarms, dio, total

    def single(self) -> list[float]:
        self.trigger()
        return self.next_values()[1]

    def check(self):
        prompt = (r := self.device.readline()).decode().strip()
        if prompt == "=>":
            return
        elif prompt == "?>":
            raise ValueError("Command error")
        elif prompt == "!>":
            raise ValueError("Execution error")
        else:
            raise ValueError(f"Unexpected response: {prompt!r}")

    def write(self, message):
        self.device.write(message.encode() + b"\r\n")
        self.check()

    def query(self, message) -> str:
        self.device.write(message.encode() + b"\r\n")
        r = self.device.readline()
        self.check()
        return r.decode().strip("\r\n")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.device.close()

    @classmethod
    def connect(cls, address: str) -> Self:
        return cls(address)
