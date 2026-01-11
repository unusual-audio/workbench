from abc import ABC
from enum import Enum
from dataclasses import dataclass

from math import sqrt, pow, log10
import threading
from typing import Self, Optional

import numpy as np
from scipy import signal
import sounddevice as sd

from workbench.instruments import Instrument
from workbench.utils import dbu_to_vrms, vrms_to_dbu, vrms_to_vpp, vpp_to_vrms


class WaveformType(Enum):
    SINE = "sine"
    SQUARE = "square"
    PULSE = "pulse"
    RAMP = "ramp"
    NOISE = "noise"
    DC = "dc"


class VoltageUnit(Enum):
    DBFS = "dbfs"
    VRMS = "vrms"
    DBU = "dbu"
    VPP = "vpp"


@dataclass
class ChannelConfig:
    sample_rate: int
    waveform: WaveformType = WaveformType.SINE
    frequency_hz: float = 1000.0
    amplitude_fs: float = 1.0
    dc_offset_fs: float = 0.0
    asymmetry: float = 0.5
    phase_deg: float = 0.0
    voltage_unit: VoltageUnit = VoltageUnit.DBFS
    calibration_vrms_at_fs: Optional[float] = None
    output_enabled: bool = False

    @property
    def period(self) -> float:
        if self.frequency_hz <= 0:
            return float("inf")
        return 1.0 / self.frequency_hz

    @period.setter
    def period(self, period_seconds: float):
        if period_seconds <= 0:
            raise ValueError("Period must be > 0")
        self.frequency_hz = 1.0 / period_seconds

    @property
    def voltage(self) -> float:
        if self.voltage_unit == VoltageUnit.DBFS:
            if self.amplitude_fs <= 0:
                return float("-inf")
            return 20.0 * log10(self.amplitude_fs)
        if self.calibration_vrms_at_fs is None:
            raise ValueError("Not calibrated")
        vrms = self.amplitude_fs * self.calibration_vrms_at_fs
        if self.voltage_unit == VoltageUnit.VRMS:
            return vrms
        if self.voltage_unit == VoltageUnit.DBU:
            return vrms_to_dbu(vrms)
        if self.voltage_unit == VoltageUnit.VPP:
            return vrms_to_vpp(vrms)
        raise ValueError(f"Unknown voltage unit: {self.voltage_unit}")

    @voltage.setter
    def voltage(self, voltage: float):
        if self.voltage_unit == VoltageUnit.DBFS:
            self.amplitude_fs = pow(10.0, voltage / 20.0)
            return
        if self.calibration_vrms_at_fs is None:
            raise ValueError("Not calibrated")
        if self.voltage_unit == VoltageUnit.VRMS:
            vrms = voltage
        elif self.voltage_unit == VoltageUnit.DBU:
            vrms = dbu_to_vrms(voltage)
        elif self.voltage_unit == VoltageUnit.VPP:
            vrms = vpp_to_vrms(voltage)
        else:
            raise ValueError(f"Unknown voltage unit: {self.voltage_unit}")
        self.amplitude_fs = vrms / self.calibration_vrms_at_fs

    @property
    def duty_cycle(self) -> float:
        return self.asymmetry * 100.0

    @duty_cycle.setter
    def duty_cycle(self, duty_cycle_percent: float):
        if not 0 <= duty_cycle_percent <= 100:
            raise ValueError("Duty cycle must be between 0 and 100")
        self.asymmetry = duty_cycle_percent / 100.0

    @property
    def skew(self) -> float:
        return self.asymmetry * 100.0

    @skew.setter
    def skew(self, skew_percent: float):
        if not 0 <= skew_percent <= 100:
            raise ValueError("Duty cycle must be between 0 and 100")
        self.asymmetry = skew_percent / 100.0

    @property
    def pulse_width(self) -> float:
        if self.frequency_hz <= 0:
            return 0.0
        return self.asymmetry / self.frequency_hz

    @pulse_width.setter
    def pulse_width(self, pulse_width_seconds: float):
        if pulse_width_seconds < 0:
            raise ValueError("Pulse width must be >= 0")
        if self.frequency_hz <= 0:
            self.asymmetry = 0.0
            return
        asymmetry = pulse_width_seconds * self.frequency_hz
        if not 0 <= asymmetry <= 1:
            raise ValueError("Pulse width exceeds period")
        self.asymmetry = asymmetry

    @property
    def dc_offset_voltage(self) -> float:
        if self.calibration_vpeak_at_fs is None:
            return 0.0
        return self.dc_offset_fs * self.calibration_vpeak_at_fs

    @dc_offset_voltage.setter
    def dc_offset_voltage(self, volts: float):
        if self.calibration_vpeak_at_fs is None:
            raise ValueError("Not calibrated")
        self.dc_offset_fs = volts / self.calibration_vpeak_at_fs

    @property
    def calibration_vpeak_at_fs(self):
        if self.calibration_vrms_at_fs is None:
            return None
        return self.calibration_vrms_at_fs * sqrt(2)



class AudioInterface(Instrument, ABC):
    device_name: str
    sample_rate: int
    output_config: list[ChannelConfig]

    def __init__(self, device_name: str, sample_rate: int, output_channels: int):
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.output_channels = output_channels
        self.output_phases = np.zeros(output_channels)
        self.lock = threading.RLock()
        self.reset()

        self.stream = sd.OutputStream(
            device=self.device_name,
            channels=output_channels,
            samplerate=sample_rate,
            callback=self.callback)

    def reset(self):
        self.output_config = [self.get_default_channel_config(i) for i in range(self.output_channels)]
        self.output_phases = np.zeros(self.output_channels)

    def get_default_channel_config(self, channel: Optional[int] = None) -> ChannelConfig:
        config = ChannelConfig(sample_rate=self.sample_rate)
        return config

    def callback(self, out_data: np.ndarray, frame_count: int, time_info, status_flags: sd.CallbackFlags):
        with self.lock:
            out_data.fill(0)
            t = np.arange(frame_count) / self.sample_rate

            for i, config in enumerate(self.output_config):
                if not config.output_enabled:
                    continue

                frequency = config.frequency_hz
                amplitude = config.amplitude_fs
                dc_offset = config.dc_offset_fs
                asymmetry = config.asymmetry
                phase_deg = config.phase_deg

                # Base phase from accumulation
                phase_rad = self.output_phases[i]
                # Static phase offset
                offset_rad = np.deg2rad(phase_deg)

                # Continuous phase for the current block
                # omega = 2 * pi * f
                # phase(t) = omega * t + phase_initial
                phase_increment = 2 * np.pi * frequency / self.sample_rate
                p = phase_rad + phase_increment * np.arange(frame_count) + offset_rad

                if config.waveform == WaveformType.SINE:
                    data = amplitude * np.sin(p) + dc_offset
                elif config.waveform == WaveformType.SQUARE:
                    data = amplitude * signal.square(p, duty=asymmetry) + dc_offset
                elif config.waveform == WaveformType.PULSE:
                    data = amplitude * signal.square(p, duty=asymmetry) + dc_offset
                elif config.waveform == WaveformType.RAMP:
                    data = amplitude * signal.sawtooth(p, width=asymmetry) + dc_offset
                elif config.waveform == WaveformType.NOISE:
                    data = amplitude * (np.random.rand(frame_count) * 2 - 1) + dc_offset
                elif config.waveform == WaveformType.DC:
                    data = np.full(frame_count, dc_offset)
                else:
                    data = np.zeros(frame_count)

                out_data[:, i] = data

                # Update accumulated phase for next callback
                self.output_phases[i] = (phase_rad + phase_increment * frame_count) % (2*np.pi)

    def __enter__(self):
        self.stream.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stream.stop()

    @classmethod
    def connect(cls, address: str) -> Self:
        device_info = sd.query_devices(address)
        if device_info is None:
            raise IOError("Device not found")
        return cls(
            device_info["name"],
            sample_rate=int(device_info["default_samplerate"]),
            output_channels=device_info["max_output_channels"])
