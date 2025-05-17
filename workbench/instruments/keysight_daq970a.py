import io

from PIL import Image

from workbench.instruments import VisaInstrument


class KeysightDAQ970A(VisaInstrument):

    instrument_name = "Keysight DAQ970A"

    def screenshot(self) -> Image:
        self.write("HCOPy:SDUMp:DATA?")
        data = self.read_raw()
        return Image.open(io.BytesIO(data[int(data[1:2].decode()) + 2:]))
