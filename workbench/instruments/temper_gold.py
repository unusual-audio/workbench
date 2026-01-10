import struct
from typing import Optional, Self

import hid

from workbench.instruments import HIDInstrument


class TemperGold(HIDInstrument):
    instrument_name = "Temper Gold"

    def read_temperature(self, timeout: int = 1000) -> float:
        response = b""
        self.write(b"\x01\x80\x33\x01\x00\x00\x00\x00")
        while r := self.read(16, timeout):
            response += r
        return struct.unpack_from('>h', response, 2)[0] / 100

    @classmethod
    def find(cls):
        results = []
        for i in hid.enumerate(0x1a86, 0xe025):
            if i["usage_page"] == 0xff00:
                results.append(i)
        return results

    @classmethod
    def connect(cls, address: Optional[str] = None) -> Self:
        for i in cls.find():
            if address is None or address == i["path"]:
                return cls(path=i["path"])
        raise IOError("Device not found")
