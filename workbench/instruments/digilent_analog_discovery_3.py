import logging
from abc import ABC
from typing import Optional, Self

import dwfpy.bindings

from workbench.instruments import Instrument


class DWFInstrument(dwfpy.Device, Instrument, ABC):
    pass


class DigilentAnalogDiscovery3(DWFInstrument):
    instrument_name = "Digilent Analog Discovery 3"

    @classmethod
    def connect(cls, address: Optional[str] = None) -> Self:
        for i in range(dwfpy.bindings.dwf_enum(dwfpy.bindings.ENUMFILTER_TYPE & 10)):
            self = cls(device_index=i)
            if address is None or self.serial_number == address:
                return self
        raise IOError("Device not found")


logging.getLogger('dwfpy').setLevel(logging.INFO)
