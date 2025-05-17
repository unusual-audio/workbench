import abc
import typing
from abc import ABC

import dwfpy
import hid
import pyvisa.resources


class Instrument(metaclass=abc.ABCMeta):

    instrument_name: str = None

    @classmethod
    @abc.abstractmethod
    def connect(cls, address) -> typing.Self:
        pass

    def _repr_html_(self):
        """Return HTML representation for Jupyter"""
        return f"""
        <div style="background-color: #eee; padding: 24px; margin: 24px; border-radius: 12px;">
            <h3>{getattr(self, "instrument_name", None) or self.__class__.__name__}</h3>
            <p>Address: {self.resource_name}</p>
        </div>
        """


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


class DWFInstrument(dwfpy.Device, Instrument, ABC):
    pass
