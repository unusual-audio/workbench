import abc
import typing
from abc import ABC

import hid
import pyvisa.resources


class Instrument(metaclass=abc.ABCMeta):
    instrument_name: str = None

    @classmethod
    @abc.abstractmethod
    def connect(cls, address) -> typing.Self:
        pass


class VisaInstrument(Instrument, pyvisa.resources.MessageBasedResource):

    default_timeout = 60_000

    @classmethod
    def connect(cls, address) -> typing.Self:
        instrument = pyvisa.ResourceManager().open_resource(resource_name=address, resource_pyclass=cls)
        if cls.default_timeout is not None:
            instrument.timeout = cls.default_timeout
        return instrument


class HIDInstrument(hid.Device, Instrument, ABC):
    pass


class SerialInstrument(pyvisa.resources.SerialInstrument, Instrument, ABC):
    default_timeout = 60_000

    @classmethod
    def connect(cls, address) -> typing.Self:
        instrument = pyvisa.ResourceManager().open_resource(resource_name=address, resource_pyclass=cls)
        if cls.default_timeout is not None:
            instrument.timeout = cls.default_timeout
        return instrument
