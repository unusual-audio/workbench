import io

from PIL import Image

from workbench.instruments import VisaInstrument


class Keysight34461A(VisaInstrument):

    instrument_name = "Keysight 34461A"

    @property
    def display_on(self) -> bool:
        return bool(int(self.query("DISPlay:STATe?")))

    @display_on.setter
    def display_on(self, display_on: bool):
        self.write("DISPlay:STATe " + ("ON" if display_on else "OFF"))

    @property
    def display_text(self) -> str:
        return self.query("DISPlay:TEXT?").strip()[1:-1].replace("\"\"", "\"")

    @display_text.setter
    def display_text(self, display_text: str):
        self.write("DISPlay:TEXT \"" + display_text.replace("\"", "\"\"") + "\"\n")

    def screenshot(self) -> Image:
        self.write("HCOPy:SDUMp:DATA?")
        data = self.read_raw()
        return Image.open(io.BytesIO(data[int(data[1:2].decode()) + 2:]))
