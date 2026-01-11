from abc import ABC, abstractmethod
from typing import Self, Union

import pyvisa.resources
from pyvisa.highlevel import VisaLibraryBase


class Instrument(ABC):
    instrument_name: str = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @classmethod
    @abstractmethod
    def connect(cls, address) -> Self:
        pass


class VisaInstrument(Instrument, pyvisa.resources.MessageBasedResource):
    default_open_timeout = 0
    default_timeout = 60_000

    @classmethod
    def connect(cls, address: str, *, visa_library: Union[str, VisaLibraryBase] = "") -> Self:
        instrument = pyvisa.ResourceManager(visa_library).open_resource(
            resource_name=address, resource_pyclass=cls, open_timeout=cls.default_open_timeout)
        if cls.default_timeout is not None:
            instrument.timeout = cls.default_timeout
        return instrument


class SerialInstrument(pyvisa.resources.SerialInstrument, Instrument, ABC):
    default_open_timeout = 0
    default_timeout = 60_000

    @classmethod
    def connect(cls, address: str, *, visa_library: Union[str, VisaLibraryBase] = "") -> Self:
        instrument = pyvisa.ResourceManager(visa_library).open_resource(
            resource_name=address, resource_pyclass=cls, open_timeout=cls.default_open_timeout)
        if cls.default_timeout is not None:
            instrument.timeout = cls.default_timeout
        return instrument