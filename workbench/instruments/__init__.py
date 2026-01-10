from abc import ABC, abstractmethod
from typing import Optional, Self

import hid
import pyvisa.resources


class Instrument(ABC):
    instrument_name: str = None

    @classmethod
    @abstractmethod
    def connect(cls, address) -> Self:
        pass


class VisaInstrument(Instrument, pyvisa.resources.MessageBasedResource):
    default_open_timeout = 0
    default_timeout = 60_000

    @classmethod
    def connect(cls, address: str) -> Self:
        instrument = pyvisa.ResourceManager().open_resource(
            resource_name=address, resource_pyclass=cls, open_timeout=cls.default_open_timeout)
        if cls.default_timeout is not None:
            instrument.timeout = cls.default_timeout
        return instrument


class HIDInstrument(hid.Device, Instrument, ABC):
    pass


class SerialInstrument(pyvisa.resources.SerialInstrument, Instrument, ABC):
    default_timeout = 60_000

    @classmethod
    def connect(cls, address: str) -> Self:
        instrument = pyvisa.ResourceManager().open_resource(resource_name=address, resource_pyclass=cls)
        if cls.default_timeout is not None:
            instrument.timeout = cls.default_timeout
        return instrument


class RemoteInstrument(VisaInstrument):
    pass