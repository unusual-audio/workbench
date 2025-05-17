import logging

import dwfpy.bindings

from workbench.instruments import DWFInstrument


class DigilentAnalogDiscovery3(DWFInstrument):

    instrument_name = "Digilent Analog Discovery 3"

    @classmethod
    def connect(cls, address: str = None):
        for i in range(dwfpy.bindings.dwf_enum(dwfpy.bindings.ENUMFILTER_TYPE & 10)):
            self = cls(device_index=i)
            if address is None or self.serial_number == address:
                return self


logging.getLogger('dwfpy').setLevel(logging.INFO)
