import codecs
import logging
import re
import socket
import threading
from abc import ABC
from typing import Optional, Callable, List, Tuple

from workbench.instruments.audio import AudioInterface, WaveformType, VoltageUnit
from workbench.utils import vrms_to_dbu, vrms_to_vpp

SCPI_COMMANDS: dict[str, tuple[Callable, list[re.Pattern]]] = {}

ESR_OPC = 0x01
ESR_QUERY_ERROR = 0x04
ESR_DDE_ERROR = 0x08
ESR_EXEC_ERROR = 0x10
ESR_CMD_ERROR = 0x20
STB_ESB = 0x20

LOGGER = logging.getLogger(__name__)


def scpi_command(regex: str, flags: int = re.IGNORECASE):
    def decorator(func: Callable):
        if func.__qualname__ not in SCPI_COMMANDS:
            SCPI_COMMANDS[func.__qualname__] = (func, [])
        SCPI_COMMANDS[func.__qualname__][1].append(re.compile(regex, flags))
        return func

    return decorator


class SCPIError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


class ScpiInstrument(ABC):
    def __init__(self, identity: str):
        self.identity = identity
        # Find SCPI commands that have been registered with @scpi_command(...) in this or any parent class
        self.commands = []
        qualnames = [self.__class__.__qualname__] + [i.__qualname__ for i in self.__class__.__bases__]
        for qualname, (func, regexes) in SCPI_COMMANDS.items():
            if not any(qualname.startswith(i + ".") for i in qualnames):
                continue
            func = getattr(self, func.__name__)
            for regex in regexes:
                self.commands.append((regex, func))
        self.errors: List[Tuple[int, str]] = []
        self.esr: int = 0
        self.sre: int = 0

    def push_error(self, code: int, message: str):
        self.errors.append((code, message))
        if code <= -100 and code > -200:
            self.esr |= ESR_CMD_ERROR  # Command Errors
        elif code <= -200 and code > -300:
            self.esr |= ESR_EXEC_ERROR  # Execution Errors
        elif code <= -300 and code > -400:
            self.esr |= ESR_DDE_ERROR  # SCPI Specified Device-Specific Errors
        elif code <= -400:
            self.esr |= ESR_QUERY_ERROR  # Query and System Errors
        else:
            self.esr |= ESR_EXEC_ERROR

    def handle_command(self, command: str) -> Optional[str]:
        try:
            for regex, func in self.commands:
                match = regex.match(command)
                if match:
                    response = func(*match.groups())
                    return response
            self.push_error(-113, "Undefined header")
            return None
        except SCPIError as e:
            self.push_error(e.code, e.message)
            return None
        except Exception as e:
            LOGGER.exception(e)
            self.push_error(-300, "Device error")
            return None

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
            raise SCPIError(-102, "Command error (syntax error)")
        if check_range and not minimum <= value <= maximum:
            raise SCPIError(-102, "Command error (out of range)")
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
                raise SCPIError(-102, "Command error (invalid argument)")
            return minimum
        elif parameter.upper() in ("MAX", "MAXIMUM"):
            if maximum is None:
                raise SCPIError(-102, "Command error (invalid argument)")
            return maximum
        elif parameter.upper() in ("DEF", "DEFAULT"):
            if default_value is None:
                raise SCPIError(-102, "Command error (invalid argument)")
            return default_value
        try:
            value = float(parameter)
        except ValueError:
            raise SCPIError(-102, "Command error (syntax error)")
        if check_range and minimum is not None and value < minimum:
            raise SCPIError(-102, "Command error (out of range)")
        if check_range and maximum is not None and value > maximum:
            raise SCPIError(-102, "Command error (out of range)")
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
                    raise SCPIError(-102, "Command error (invalid argument)")
                return str(minimum)
            if parameter.upper() in ("MAX", "MAXIMUM"):
                if maximum is None:
                    raise SCPIError(-102, "Command error (invalid argument)")
                return str(maximum)
            if parameter.upper() in ("DEF", "DEFAULT"):
                if default_value is None:
                    raise SCPIError(-102, "Command error (invalid argument)")
                return str(default_value)
        return str(current_value)

    @scpi_command(r"^\*IDN\?$")
    def get_identity(self) -> str:
        """
        *IDN?
        """
        return self.identity

    @scpi_command(r"^\*OPC\?$")
    def get_operation_complete(self) -> str:
        """
        *OPC?
        """
        self.esr |= ESR_OPC
        return "1"

    @scpi_command(r"^\*RST$")
    def reset(self) -> None:
        """
        *RST
        """
        self.clear_status()

    @scpi_command(r"^\*CLS$")
    def clear_status(self) -> None:
        """
        *CLS
        """
        self.errors.clear()
        self.esr = 0

    @scpi_command(r"^\*ESR\?$")
    def esr_query(self) -> str:
        """
        *ESR?
        """
        response = str(self.esr)
        self.esr = 0
        return response

    @scpi_command(r"^\*SRE\s+(\d+)$")
    def sre_set(self, mask: str) -> str:
        """
        *SRE <data>
        """
        self.sre = int(mask) & 0xFF
        return ""

    @scpi_command(r"^\*SRE\?$")
    def sre_query(self) -> str:
        """
        *SRE?
        """
        return str(self.sre)

    @scpi_command(r"^\*STB\?$")
    def stb_query(self) -> str:
        """
        *STB?
        """
        stb = 0
        if self.esr & self.sre:
            stb |= STB_ESB
        return str(stb)

    @scpi_command(r"^SYST(?:em)?:ERR(?:or)?\?$")
    def get_system_error(self) -> str:
        """
        SYSTem:ERRor?
        """
        if self.errors:
            status, message = self.errors.pop(0)
        else:
            status, message = 0, "No error"
        return f"{status},\"{str(message)}\""


class ScpiSignalGenerator(ScpiInstrument):
    WAVEFORM_MAP = {
        WaveformType.SINE: ("SINusoid", ("SIN", "SINUSOID")),
        WaveformType.SQUARE: ("SQUare", ("SQU", "SQUARE")),
        WaveformType.PULSE: ("PULSe", ("PUL", "PULSE")),
        WaveformType.RAMP: ("RAMP", ("RAMP",)),
        WaveformType.NOISE: ("NOISe", ("NOI", "NOISE")),
        WaveformType.DC: ("DC", ("DC",)),
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
                raise SCPIError(-102, "Invalid parameter (not calibrated)")

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
                raise SCPIError(-102, "Invalid parameter")

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
            raise SCPIError(-102, "Invalid parameter")
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
        [SOURce<n>:]FUNCtion {SINusoid|SQUare|PULSe|TRIangle|NOISe|DC}
        """
        channel = self.get_channel(channel_str)
        param_upper = parameter.upper()
        for waveform, (scpi_name, aliases) in self.WAVEFORM_MAP.items():
            if param_upper in aliases:
                self.audio_interface.output_config[channel].waveform = waveform
                return None
        raise SCPIError(-102, "Invalid parameter")

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?FUNC(?:tion)?\?$")
    def get_source_function_command(self, channel_str: Optional[str]) -> str:
        """
        [SOURce<n>:]FUNCtion?
        """
        channel = self.get_channel(channel_str)
        waveform = self.audio_interface.output_config[channel].waveform
        if waveform in self.WAVEFORM_MAP:
            return self.WAVEFORM_MAP[waveform][0]
        raise SCPIError(-102, "Invalid parameter")

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
                    raise SCPIError(-102, "Invalid parameter (not calibrated)")
                self.audio_interface.output_config[channel].voltage_unit = unit
                return None
        raise SCPIError(-102, "Invalid parameter")

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?:UNIT\?$")
    def get_source_voltage_unit_command(self, channel_str: Optional[str]) -> str:
        """
        [SOURce<n>:]VOLTage:UNIT?
        """
        channel = self.get_channel(channel_str)
        voltage_unit = self.audio_interface.output_config[channel].voltage_unit
        if voltage_unit in self.VOLTAGE_UNIT_MAP:
            return self.VOLTAGE_UNIT_MAP[voltage_unit][0]
        raise SCPIError(-102, "Invalid parameter")

    @scpi_command(r"^(?:SOUR(?:ce)?(\d+)?:)?VOLT(?:age)?:OFFS(?:et)?\s+(\S+)$")
    def set_source_dc_offset_command(self, channel_str: Optional[str], parameter: str):
        """
        [SOURce<n>:]VOLTage:OFFSet {<voltage>|MINimum|MAXimum|DEFault}
        """
        channel = self.get_channel(channel_str)
        if self.audio_interface.output_config[channel].calibration_vrms_at_fs is None:
            raise SCPIError(-102, "Invalid parameter (not calibrated)")
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
            raise SCPIError(-102, "Invalid parameter (not calibrated)")
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


class ScpiServer:
    def __init__(self, device: ScpiInstrument):
        self.device = device

    def start(self, host: str = "", port: int = 5025):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            s.listen()
            while True:
                connection, address = s.accept()
                threading.Thread(target=self.client_thread, args=(connection, address,), daemon=True).start()

    def client_thread(self, connection, address):
        with connection:
            decoder = codecs.getincrementaldecoder("utf-8")()
            buffer = ""
            while True:
                try:
                    data = connection.recv(1024)
                except ConnectionResetError:
                    return
                if not data:
                    break
                buffer += decoder.decode(data)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    command = line.strip()
                    if not command:
                        continue
                    response = self.device.handle_command(command)
                    if response is not None:
                        connection.sendall(response.encode() + b"\n")
