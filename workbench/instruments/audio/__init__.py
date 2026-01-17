from abc import ABC
from enum import Enum
from dataclasses import dataclass

from math import sqrt, pow, log10
import threading
from typing import Self, Optional, Tuple

import numpy as np
from scipy.signal import square, sawtooth, chirp
import sounddevice as sd

from workbench.instruments import Instrument
from workbench.utils import dbu_to_vrms, vrms_to_dbu, vrms_to_vpp, vpp_to_vrms
from workbench.utils.server import ScpiInstrument, scpi_command, SCPIError


class WaveformType(Enum):
    SINE = "sine"
    SQUARE = "square"
    PULSE = "pulse"
    RAMP = "ramp"
    NOISE = "noise"
    DC = "dc"
    SWEEP = "sweep"
    IMPULSE = "impulse"


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
    sweep_start_frequency_hz: float = 200.0
    sweep_stop_frequency_hz: float = 20_000.0
    sweep_duration_s: float = 1.0

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
            raise ValueError("Skew must be between 0 and 100")
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
        self.sweep_times = np.zeros(output_channels)
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
        self.sweep_times = np.zeros(self.output_channels)

    def get_default_channel_config(self, channel: Optional[int] = None) -> ChannelConfig:
        config = ChannelConfig(sample_rate=self.sample_rate)
        return config

    def callback(self, out_data: np.ndarray, frame_count: int, time_info, status_flags: sd.CallbackFlags):
        with self.lock:
            out_data.fill(0)

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
                    data = amplitude * square(p, duty=asymmetry) + dc_offset
                elif config.waveform == WaveformType.PULSE:
                    data = amplitude * square(p, duty=asymmetry) + dc_offset
                elif config.waveform == WaveformType.RAMP:
                    data = amplitude * sawtooth(p, width=asymmetry) + dc_offset
                elif config.waveform == WaveformType.NOISE:
                    data = amplitude * (np.random.rand(frame_count) * 2 - 1) + dc_offset
                elif config.waveform == WaveformType.DC:
                    data = np.full(frame_count, dc_offset)
                elif config.waveform == WaveformType.SWEEP:
                    data = amplitude * chirp(
                        (self.sweep_times[i] + (np.arange(frame_count) / self.sample_rate)) % config.sweep_duration_s,
                        config.sweep_start_frequency_hz,
                        config.sweep_duration_s,
                        config.sweep_stop_frequency_hz,
                        phi=phase_deg,
                    ) + dc_offset
                    self.sweep_times[i] = (
                            (self.sweep_times[i] + frame_count / self.sample_rate) % config.sweep_duration_s)
                elif config.waveform == WaveformType.IMPULSE:
                    data = np.full(frame_count, dc_offset)
                    cycle_idx = np.floor(p / (2 * np.pi))
                    prev_cycle_idx = np.floor((phase_rad + offset_rad - phase_increment) / (2 * np.pi))
                    data[np.diff(cycle_idx, prepend=prev_cycle_idx) > 0] += amplitude
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
        self.stream.close()

    @classmethod
    def connect(cls, address: str) -> Self:
        device_info = sd.query_devices(address)
        if device_info is None:
            raise IOError("Device not found")
        return cls(
            device_info["name"],
            sample_rate=int(device_info["default_samplerate"]),
            output_channels=device_info["max_output_channels"])


class ScpiSignalGenerator(ScpiInstrument):
    WAVEFORM_MAP = {
        WaveformType.SINE: ("SINusoid", ("SIN", "SINUSOID")),
        WaveformType.SQUARE: ("SQUare", ("SQU", "SQUARE")),
        WaveformType.PULSE: ("PULSe", ("PUL", "PULSE")),
        WaveformType.RAMP: ("RAMP", ("RAMP",)),
        WaveformType.NOISE: ("NOISe", ("NOI", "NOISE")),
        WaveformType.DC: ("DC", ("DC",)),
        WaveformType.SWEEP: ("SWEep", ("SWE", "SWEEP")),
        WaveformType.IMPULSE: ("IMPulse", ("IMP", "IMPULSE")),
    }

    VOLTAGE_UNIT_MAP = {
        VoltageUnit.DBFS: ("dBFS", ("DBFS",)),
        VoltageUnit.VRMS: ("Vrms", ("VRMS",)),
        VoltageUnit.DBU: ("dBu", ("DBU",)),
        VoltageUnit.VPP: ("Vpp", ("VPP",)),
    }

    def __init__(self, audio_interface: AudioInterface, identity: str):
        super().__init__(identity)
        self.audio_interface = audio_interface
        self.default_channel_config = audio_interface.get_default_channel_config()

    def handle_command(self, command: str) -> Optional[str]:
        with self.audio_interface.lock:
            return super().handle_command(command)

    @scpi_command(r"^\*RST$")
    def reset(self):
        """
        *RST
        """
        super().reset()
        self.audio_interface.reset()

    @staticmethod
    def get_int_parameter(
            parameter: str,
            minimum: int,
            maximum: int,
            default_value: int,
            check_range: bool = True,
    ) -> int:
        if parameter.upper() in ("MIN", "MINIMUM"):
            return minimum
        elif parameter.upper() in ("MAX", "MAXIMUM"):
            return maximum
        elif parameter.upper() in ("DEF", "DEFAULT"):
            return default_value
        try:
            value = int(parameter)
        except ValueError:
            raise SCPIError(-104, "Data type error")
        if check_range and not minimum <= value <= maximum:
            raise SCPIError(-222, "Data out of range")
        return value

    @staticmethod
    def get_float_parameter(
            parameter: str,
            minimum: Optional[float],
            maximum: Optional[float],
            default_value: Optional[float],
            check_range: bool = True,
    ) -> float:
        if parameter.upper() in ("MIN", "MINIMUM"):
            if minimum is None:
                raise SCPIError(-108, "Parameter not allowed")
            return minimum
        elif parameter.upper() in ("MAX", "MAXIMUM"):
            if maximum is None:
                raise SCPIError(-108, "Parameter not allowed")
            return maximum
        elif parameter.upper() in ("DEF", "DEFAULT"):
            if default_value is None:
                raise SCPIError(-108, "Parameter not allowed")
            return default_value
        try:
            value = float(parameter)
        except ValueError:
            raise SCPIError(-104, "Data type error")
        if check_range and minimum is not None and value < minimum:
            raise SCPIError(-222, "Data out of range")
        if check_range and maximum is not None and value > maximum:
            raise SCPIError(-222, "Data out of range")
        return value

    @staticmethod
    def get_float_parameter_value(
            parameter: Optional[str],
            minimum: Optional[float],
            maximum: Optional[float],
            default_value: Optional[float],
            current_value: float,
    ) -> str:
        if parameter:
            if parameter.upper() in ("MIN", "MINIMUM"):
                if minimum is None:
                    raise SCPIError(-108, "Parameter not allowed")
                return str(minimum)
            if parameter.upper() in ("MAX", "MAXIMUM"):
                if maximum is None:
                    raise SCPIError(-108, "Parameter not allowed")
                return str(maximum)
            if parameter.upper() in ("DEF", "DEFAULT"):
                if default_value is None:
                    raise SCPIError(-108, "Parameter not allowed")
                return str(default_value)
            raise SCPIError(-108, "Parameter not allowed")
        return str(current_value)

    def get_channel(self, parameter: Optional[str]) -> int:
        minimum = 1
        maximum = len(self.audio_interface.output_config)
        return self.get_int_parameter(parameter or "1", minimum, maximum, minimum) - 1

    def get_voltage_limits(self, channel: int) -> Tuple[float, float, float]:
        channel_config = self.audio_interface.output_config[channel]
        default_config = self.audio_interface.get_default_channel_config(channel)

        if channel_config.voltage_unit == VoltageUnit.DBFS:
            minimum = float("-inf")
            maximum = 0.0
            default_config.voltage_unit = VoltageUnit.DBFS
            default_value = default_config.voltage
        else:
            vrms_at_fs = channel_config.calibration_vrms_at_fs
            if vrms_at_fs is None:
                raise SCPIError(-221, "Settings conflict (not calibrated)")

            if channel_config.voltage_unit == VoltageUnit.VRMS:
                minimum = 0.0
                maximum = vrms_at_fs
                default_config.calibration_vrms_at_fs = vrms_at_fs
                default_config.voltage_unit = VoltageUnit.VRMS
                default_value = default_config.voltage
            elif channel_config.voltage_unit == VoltageUnit.DBU:
                minimum = float("-inf")
                maximum = vrms_to_dbu(vrms_at_fs)
                default_config.calibration_vrms_at_fs = vrms_at_fs
                default_config.voltage_unit = VoltageUnit.DBU
                default_value = default_config.voltage
            elif channel_config.voltage_unit == VoltageUnit.VPP:
                minimum = 0.0
                maximum = vrms_to_vpp(vrms_at_fs)
                default_config.calibration_vrms_at_fs = vrms_at_fs
                default_config.voltage_unit = VoltageUnit.VPP
                default_value = default_config.voltage
            else:
                raise SCPIError(-224, "Illegal parameter value")

        return minimum, maximum, default_value

    @scpi_command(r"^OUTP(?:ut)?(\d+)?\s+(ON|OFF|[01])$")
    def set_output_enabled_command(self, channel_str: Optional[str], parameter: str):
        """
        OUTPut[<n>] {ON|OFF|1|0}
        """
        channel = self.get_channel(channel_str)
        if parameter.upper() in ("ON", "1"):
            self.audio_interface.output_config[channel].output_enabled = True
        elif parameter.upper() in ("OFF", "0"):
            self.audio_interface.output_config[channel].output_enabled = False
        else:
            raise SCPIError(-224, "Illegal parameter value")
        return None

    @scpi_command(r"^OUTP(?:ut)?(\d+)?\?$")
    def get_output_enabled_command(self, channel_str: Optional[str]) -> str:
        """
        OUTPut[<n>]?
        """
        channel = self.get_channel(channel_str)
        return "1" if self.audio_interface.output_config[channel].output_enabled else "0"

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?\s+(\w+)$")
    def set_source_function_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]FUNCtion {SINusoid|SQUare|PULSe|RAMP|NOISe|DC|SWEep|IMPulse}
        """
        channel = self.get_channel(channel_str)
        param_upper = parameter.upper()
        for waveform, (scpi_name, aliases) in self.WAVEFORM_MAP.items():
            if param_upper in aliases:
                self.audio_interface.output_config[channel].waveform = waveform
                return None
        raise SCPIError(-224, "Illegal parameter value")

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?\?$")
    def get_source_function_command(self, channel_str: Optional[str]) -> str:
        """
        [SOURce<n>:]FUNCtion?
        """
        channel = self.get_channel(channel_str)
        waveform = self.audio_interface.output_config[channel].waveform
        if waveform in self.WAVEFORM_MAP:
            return self.WAVEFORM_MAP[waveform][0]
        raise SCPIError(-224, "Illegal parameter value")

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FREQ(?:uency)?\s+(\S+)$")
    def set_source_frequency_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]FREQuency {<frequency>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = self.audio_interface.sample_rate / 2.0
        frequency = self.get_float_parameter(parameter, minimum, maximum, self.default_channel_config.frequency_hz)
        self.audio_interface.output_config[channel].frequency_hz = frequency
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FREQ(?:uency)?\?(?:\s+(\S+))?$")
    def get_source_frequency_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]FREQuency? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = self.audio_interface.sample_rate / 2.0
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.frequency_hz,
            self.audio_interface.output_config[channel].frequency_hz)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?\s+(\S+)$")
    def set_source_voltage_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]VOLTage {<voltage>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum, maximum, default_value = self.get_voltage_limits(channel)
        voltage = self.get_float_parameter(parameter, minimum, maximum, default_value)
        self.audio_interface.output_config[channel].voltage = voltage
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?\?(?:\s+(\S+))?$")
    def get_source_voltage_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]VOLTage? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum, maximum, default_value = self.get_voltage_limits(channel)
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            default_value,
            self.audio_interface.output_config[channel].voltage)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?:UNIT\s+(\w+)$")
    def set_source_voltage_unit_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]VOLTage:UNIT {dBFS|Vrms|dBu|Vpp}
        """
        channel = self.get_channel(channel_str)
        param_upper = parameter.upper()
        for unit, (scpi_name, aliases) in self.VOLTAGE_UNIT_MAP.items():
            if param_upper in aliases:
                if unit != VoltageUnit.DBFS and self.audio_interface.output_config[
                    channel].calibration_vrms_at_fs is None:
                    raise SCPIError(-221, "Settings conflict (not calibrated)")
                self.audio_interface.output_config[channel].voltage_unit = unit
                return None
        raise SCPIError(-224, "Illegal parameter value")

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?:UNIT\?$")
    def get_source_voltage_unit_command(self, channel_str: Optional[str]) -> str:
        """
        [SOURce<n>:]VOLTage:UNIT?
        """
        channel = self.get_channel(channel_str)
        voltage_unit = self.audio_interface.output_config[channel].voltage_unit
        if voltage_unit in self.VOLTAGE_UNIT_MAP:
            return self.VOLTAGE_UNIT_MAP[voltage_unit][0]
        raise SCPIError(-224, "Illegal parameter value")

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?:OFFS(?:et)?\s+(\S+)$")
    def set_source_dc_offset_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]VOLTage:OFFSet {<voltage>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        if self.audio_interface.output_config[channel].calibration_vrms_at_fs is None:
            raise SCPIError(-221, "Settings conflict (not calibrated)")
        minimum = -self.audio_interface.output_config[channel].calibration_vpeak_at_fs
        maximum = +self.audio_interface.output_config[channel].calibration_vpeak_at_fs
        dc_offset_voltage = self.get_float_parameter(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.dc_offset_voltage)
        self.audio_interface.output_config[channel].dc_offset_voltage = dc_offset_voltage
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?:OFFS(?:et)?\?(?:\s+(\S+))?$")
    def get_source_dc_offset_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]VOLTage:OFFSet? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        if self.audio_interface.output_config[channel].calibration_vrms_at_fs is None and parameter is None:
            return "0"
        minimum = None
        maximum = None
        if self.audio_interface.output_config[channel].calibration_vrms_at_fs is not None:
            minimum = -self.audio_interface.output_config[channel].calibration_vpeak_at_fs
            maximum = +self.audio_interface.output_config[channel].calibration_vpeak_at_fs
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.dc_offset_voltage,
            self.audio_interface.output_config[channel].dc_offset_voltage)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?:CAL(?:ibration)?\s+(\S+)$")
    def set_source_calibration_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]VOLTage:CALibration {<voltage>|DEFault}
        """
        channel = self.get_channel(channel_str)
        default_config = self.audio_interface.get_default_channel_config(channel)
        calibration_vrms_at_fs = self.get_float_parameter(
            parameter,
            None,
            None,
            default_config.calibration_vrms_at_fs)
        self.audio_interface.output_config[channel].calibration_vrms_at_fs = calibration_vrms_at_fs
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?:CAL(?:ibration)?\?(?:\s+(\S+))?$")
    def get_source_calibration_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]VOLTage:CALibration? [DEFault]
        """
        channel = self.get_channel(channel_str)
        default_config = self.audio_interface.get_default_channel_config(channel)
        if self.audio_interface.output_config[channel].calibration_vrms_at_fs is None:
            raise SCPIError(-221, "Settings conflict (not calibrated)")
        return self.get_float_parameter_value(
            parameter,
            None,
            None,
            default_config.calibration_vrms_at_fs,
            self.audio_interface.output_config[channel].calibration_vrms_at_fs)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?:RAMP:SYMM(?:etry)?\s+(\S+)$")
    def set_source_asymmetry_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]FUNCtion:RAMP:SYMMetry {<percent>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = 100.0
        skew = self.get_float_parameter(parameter, minimum, maximum, self.default_channel_config.skew)
        self.audio_interface.output_config[channel].skew = skew
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?:RAMP:SYMM(?:etry)?\?(?:\s+(\S+))?$")
    def get_source_asymmetry_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]FUNCtion:RAMP:SYMMetry? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = 100.0
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.skew,
            self.audio_interface.output_config[channel].skew)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?PHAS(?:e)?\s+(\S+)$")
    def set_source_phase_deg_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]PHASe {<angle>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = -360.0
        maximum = +360.0
        phase_deg = self.get_float_parameter(parameter, minimum, maximum, self.default_channel_config.phase_deg)
        self.audio_interface.output_config[channel].phase_deg = phase_deg
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?PHAS(?:e)?\?(?:\s+(\S+))?$")
    def get_source_phase_deg_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]PHASe? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = -360.0
        maximum = +360.0
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.phase_deg,
            self.audio_interface.output_config[channel].phase_deg)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?PER(?:iod)?\s+(\S+)$")
    def set_source_period_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]PERiod {<seconds>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = 1 / self.audio_interface.sample_rate
        maximum = float("inf")
        period = self.get_float_parameter(parameter, minimum, maximum, self.default_channel_config.period)
        self.audio_interface.output_config[channel].period = period
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?PER(?:iod)?\?(?:\s+(\S+))?$")
    def get_source_period_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]PERiod? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = 1 / self.audio_interface.sample_rate
        maximum = float("inf")
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.period,
            self.audio_interface.output_config[channel].period)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?:SQU(?:are):DCYC(?:le)?\s+(\S+)$")
    def set_source_duty_cycle_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]FUNCtion:SQUare:DCYCle {<percent>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = 100.0
        duty_cycle = self.get_float_parameter(parameter, minimum, maximum, self.default_channel_config.duty_cycle)
        self.audio_interface.output_config[channel].duty_cycle = duty_cycle
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?:SQU(?:are):DCYC(?:le)?\?(?:\s+(\S+))?$")
    def get_source_duty_cycle_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]FUNCtion:SQUare:DCYCle? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = 100.0
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.duty_cycle,
            self.audio_interface.output_config[channel].duty_cycle)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?:PUL(?:se):PWID(?:th)?\s+(\S+)$")
    def set_source_pulse_width_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]FUNCtion:PULse:PWIDth {<seconds>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = self.audio_interface.output_config[channel].period
        pulse_width = self.get_float_parameter(parameter, minimum, maximum, self.default_channel_config.pulse_width)
        self.audio_interface.output_config[channel].pulse_width = pulse_width
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?:PUL(?:se):PWID(?:th)?\?(?:\s+(\S+))?$")
    def get_source_pulse_width_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]FUNCtion:PULse:PWIDth? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = self.audio_interface.output_config[channel].period
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.pulse_width,
            self.audio_interface.output_config[channel].pulse_width)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion):SWE(?:ep):FREQ(?:uency)?:STAR(?:t)?\s+(\S+)$")
    def set_source_sweep_start_frequency_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]FUNCtion:SWEep:FREQuency:STARt {<frequency>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = self.audio_interface.sample_rate / 2.0
        frequency = self.get_float_parameter(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.sweep_start_frequency_hz)
        self.audio_interface.output_config[channel].sweep_start_frequency_hz = frequency
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion):SWE(?:ep):FREQ(?:uency)?:STAR(?:t)?\?(?:\s+(\S+))?$")
    def get_source_sweep_start_frequency_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]FUNCtion:SWEep:FREQuency:STARt? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = self.audio_interface.sample_rate / 2.0
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.sweep_start_frequency_hz,
            self.audio_interface.output_config[channel].sweep_start_frequency_hz)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion):SWE(?:ep):FREQ(?:uency)?:STOP\s+(\S+)$")
    def set_source_sweep_stop_frequency_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]FUNCtion:SWEep:FREQuency:STOP {<frequency>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = self.audio_interface.sample_rate / 2.0
        frequency = self.get_float_parameter(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.sweep_stop_frequency_hz)
        self.audio_interface.output_config[channel].sweep_stop_frequency_hz = frequency
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion):SWE(?:ep):FREQ(?:uency)?:STOP\?(?:\s+(\S+))?$")
    def get_source_sweep_stop_frequency_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]FUNCtion:SWEep:FREQuency:STOP? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = 0.0
        maximum = self.audio_interface.sample_rate / 2.0
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.sweep_stop_frequency_hz,
            self.audio_interface.output_config[channel].sweep_stop_frequency_hz)

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?:SWE(?:ep)?:TIME\s+(\S+)$")
    def set_source_sweep_time_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]FUNCtion:SWEep:TIME {<seconds>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        minimum = 1e-3
        maximum = 1000.0
        duration = self.get_float_parameter(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.sweep_duration_s)
        self.audio_interface.output_config[channel].sweep_duration_s = duration
        return None

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?:SWE(?:ep)?:TIME\?(?:\s+(\S+))?$")
    def get_source_sweep_time_command(self, channel_str: Optional[str], parameter: Optional[str]) -> str:
        """
        [SOURce<n>:]FUNCtion:SWEep:TIME? [{MINimum|MAXimum|DEFault}]
        """
        channel = self.get_channel(channel_str)
        minimum = 1e-3
        maximum = 1000.0
        return self.get_float_parameter_value(
            parameter,
            minimum,
            maximum,
            self.default_channel_config.sweep_duration_s,
            self.audio_interface.output_config[channel].sweep_duration_s)
