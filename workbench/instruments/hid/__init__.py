from abc import ABC

import hid

from workbench.instruments import Instrument


class HIDInstrument(hid.Device, Instrument, ABC):
    pass
