from typing import Self, Tuple, Iterator, Optional

import hid

from workbench.instruments import HIDInstrument


class BrymenBM869S(HIDInstrument):
    class Display:
        chars = {
            0b0000000: ' ',
            0b0100000: '-',
            0b1011111: '0',
            0b1010000: '1',
            0b1101101: '2',
            0b1111100: '3',
            0b1110010: '4',
            0b0111110: '5',
            0b0111111: '6',
            0b1010100: '7',
            0b1111111: '8',
            0b1111110: '9',
            0b0001111: 'C',
            0b0100111: 'F',
            0b0001011: 'L',
            0b1111001: "d",
            0b0010000: "i",
            0b0111001: "o",
            0b0101111: "E",
            0b0100001: "r",
            0b0110001: "n",
        }

        instrument_name = "Brymen BM869S"

        def __init__(self, reply):
            self.reply = reply

        @property
        def primary_display(self) -> str:
            return "".join([
                "-" if self.reply[2] & 0b10000000 else "",
                self.chars.get(self.reply[3] >> 1, ""),
                "." if self.reply[4] & 1 else "",
                self.chars.get(self.reply[4] >> 1, ""),
                "." if self.reply[5] & 1 else "",
                self.chars.get(self.reply[5] >> 1, ""),
                "." if self.reply[6] & 1 else "",
                self.chars.get(self.reply[6] >> 1, ""),
                "." if self.reply[7] & 1 else "",
                self.chars.get(self.reply[7] >> 1, ""),
                self.chars.get(self.reply[8] >> 1, ""),
            ]).strip().rstrip("CF-")

        @property
        def secondary_display(self) -> str:
            return "".join([
                "-" if self.reply[9] & 0b10000000 else "",
                self.chars[self.reply[10] >> 1],
                "." if self.reply[11] & 1 else "",
                self.chars[self.reply[11] >> 1],
                "." if self.reply[12] & 1 else "",
                self.chars[self.reply[12] >> 1],
                "." if self.reply[13] & 1 else "",
                self.chars[self.reply[13] >> 1],
            ]).strip()

    def read_displays(self, timeout: int = 4000) -> Tuple[str, str]:
        self.write(b"\x00\x00\x86\x66")
        reply = b""
        reply += self.read(8, timeout)
        reply += self.read(8, timeout)
        reply += self.read(8, timeout)
        display = BrymenBM869S.Display(reply)
        return display.primary_display, display.secondary_display

    def read_display(self, timeout: int = 4000):
        primary_display, _ = self.read_displays(timeout=timeout)
        return primary_display

    @classmethod
    def connect(cls, address: Optional[str] = None) -> Self:
        for i in cls.enumerate():
            if address is None or i["serial_number"] == address:
                return cls(path=i["path"])
        raise IOError("Device not found")

    @classmethod
    def enumerate(cls) -> Iterator[dict]:
        for i in hid.enumerate(0x0820, 0x0001):
            yield i
