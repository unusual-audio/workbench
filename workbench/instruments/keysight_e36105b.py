import typing

from workbench.instruments import VisaInstrument


class KeysightE36105B(VisaInstrument):
    instrument_name = "Keysight E36105B"

    @classmethod
    def connect(cls, address, open_timeout=5000, **kwargs) -> typing.Self:
        return super(KeysightE36105B, cls).connect(address, open_timeout=open_timeout, **kwargs)