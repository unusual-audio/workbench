from __future__ import annotations

import dataclasses
import typing

import hid

from workbench.instruments import HIDInstrument


class BA63(HIDInstrument):
    class Encoding:
        @dataclasses.dataclass
        class Encoding:
            country_code: int
            code_page: str

        default = Encoding(0x30, "cp437")
        latin_1 = Encoding(0x31, "cp850")
        latin_2 = Encoding(0x32, "cp852")
        latin_5_turkey = Encoding(0x33, "cp857")
        latin_1_euro = Encoding(0x34, "cp858")
        latin_cyrillic = Encoding(0x35, "cp866")
        latin_hebrew = Encoding(0x37, "cp862")
        latin_greek_2 = Encoding(0x36, "cp737")
        katakana = Encoding(0x63, "cp857")

    instrument_name = "Wincor Nixdorf BA63"

    def __init__(self, vid=None, pid=None, serial=None, path=None):
        super().__init__(vid, pid, serial, path)
        self.country = None

    def clear(self):
        self.write_bytes(bytes([0x1B, 0x5B, 0x32, 0x4A]))

    def set_encoding(self, country: Encoding.Encoding):
        self.country = country
        self.write_bytes(bytes([0x1B, 0x52, self.country.country_code]))

    def set_cursor_position(self, row: int, column: int = 1):
        self.write_bytes(bytes([0x1B, 0x5B, 0x30 + row, 0x3B, 0x30 + column, 0x48]))

    def write_text(self, text: str):
        if self.country is None:
            self.set_encoding(BA63.Encoding.default)
        self.write_bytes(text.encode(self.country.code_page))

    def write_text_at(self, text: str, row: int, column: int = 1):
        self.set_cursor_position(row, column)
        self.write_text(text)

    def write_bytes(self, sequence: bytes):
        self.write(bytes([0x02, 0x00, len(sequence)]) + sequence)

    def write_bytes_at(self, sequence: bytes, row: int, column: int = 1):
        self.set_cursor_position(row, column)
        self.write_bytes(sequence)

    @classmethod
    def find(cls):
        results = []
        for i in hid.enumerate(0xaa7, 0x200):
            if i["usage_page"] == 0xff45:
                results.append(i)
        return results

    @classmethod
    def connect(cls, address: str = None) -> typing.Self:
        for i in cls.find():
            if (address is None or address == i["path"]) and i["interface_number"] == 1:
                return cls(path=i["path"])
        raise IOError("Device not found")
