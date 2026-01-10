from typing import Optional, Self

from workbench.instruments import VisaInstrument


class KeysightE36105B(VisaInstrument):
    default_open_timeout = 5000
    instrument_name = "Keysight E36105B"