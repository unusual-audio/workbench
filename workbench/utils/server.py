import codecs
import logging
import re
import socket
import threading
from abc import ABC
from typing import Optional, Callable, List, Tuple

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
