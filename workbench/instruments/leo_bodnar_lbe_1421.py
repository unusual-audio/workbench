import typing

import hid

from workbench.instruments import HIDInstrument


class LeoBodNaLB1421(HIDInstrument):

    @classmethod
    def find(cls):
        results = []
        for i in hid.enumerate(0x1dd2, 0x2444):
            results.append(i)
        return results

    @classmethod
    def connect(cls, address: str = None) -> typing.Self:
        for i in cls.find():
            if (address is None or address == i["path"]):
                return cls(path=i["path"])
        raise IOError("Device not found")
