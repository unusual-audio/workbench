from enum import Enum
from dataclasses import dataclass
from typing import Self

import numpy as np
import sounddevice as sd

from workbench.instruments import Instrument


class WaveformType(Enum):
    SINE = "sine"
    SQUARE = "square"
    PULSE = "pulse"
    NOISE = "noise"


@dataclass
class ChannelConfig:
    waveform: WaveformType = WaveformType.SINE
    frequency: float = 1000.0
    amplitude: float = 0.0  # Linear Full Scale
    duty_cycle: float = 0.5
    phase_offset: float = 0.0
    enabled: bool = False


class AudioInterface(Instrument):
    def __init__(self, device_name: str, sample_rate: int, output_channels: int):
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.output_channels = output_channels
        self.output_config = [ChannelConfig() for _ in range(output_channels)]
        self.output_phase = np.zeros(output_channels)

        self.stream = sd.OutputStream(
            device=self.device_name,
            channels=output_channels,
            samplerate=sample_rate,
            callback=self._callback)


    def _callback(self, out_data: np.ndarray, frame_count: int, time_info, status_flags: sd.CallbackFlags):
        out_data.fill(0)
        t = (np.arange(frame_count) / self.sample_rate)

        for i, config in enumerate(self.output_config):
            if not config.enabled or config.amplitude == 0:
                self.output_phase[i] = (self.output_phase[i] + frame_count * config.frequency / self.sample_rate) % 1.0
                continue

            peak = config.amplitude
            phase = (self.output_phase[i] + t * config.frequency + config.phase_offset) % 1.0

            if config.waveform == WaveformType.SINE:
                out_data[:, i] = peak * np.sin(2 * np.pi * phase)
            elif config.waveform == WaveformType.SQUARE:
                out_data[:, i] = peak * np.where(phase < 0.5, 1.0, -1.0)
            elif config.waveform == WaveformType.PULSE:
                out_data[:, i] = peak * np.where(phase < config.duty_cycle, 1.0, -1.0)
            elif config.waveform == WaveformType.NOISE:
                out_data[:, i] = peak * np.random.normal(0, 1, frame_count)  # config.amplitude as RMS

            self.output_phase[i] = (self.output_phase[i] + frame_count * config.frequency / self.sample_rate) % 1.0

    def set_waveform(self, channel: int, waveform: WaveformType):
        self.output_config[channel].waveform = waveform

    def set_frequency(self, channel: int, frequency: float):
        self.output_config[channel].frequency = frequency

    def set_amplitude(self, channel: int, amplitude: float):
        self.output_config[channel].amplitude = amplitude

    def set_duty_cycle(self, channel: int, duty_cycle: float):
        self.output_config[channel].duty_cycle = duty_cycle

    def set_phase(self, channel: int, phase_offset: float):
        self.output_config[channel].phase_offset = phase_offset

    def enable_output(self, channel: int, enable: bool = True):
        self.output_config[channel].enabled = enable

    def __enter__(self):
        self.stream.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stream.stop()

    @classmethod
    def connect(cls, address: str = "UltraLite-mk5") -> Self:
        device_info = sd.query_devices(address)
        if device_info is None:
            raise IOError("Device not found")
        return cls(
            device_info["name"],
            sample_rate=int(device_info["default_samplerate"]),
            output_channels=device_info["max_output_channels"])


if __name__ == "__main__":
    with MOTOUltraLiteMk5.connect() as motu_ultralite_mk5:
        motu_ultralite_mk5.set_waveform(3, WaveformType.SINE)
        motu_ultralite_mk5.set_frequency(3, 440.0)
        motu_ultralite_mk5.set_amplitude(3, 0.5)
        motu_ultralite_mk5.enable_output(3)
