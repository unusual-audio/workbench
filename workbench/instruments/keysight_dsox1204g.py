import io

from PIL import Image

from workbench.instruments import VisaInstrument


class KeysightDSOX1204G(VisaInstrument):
    instrument_name = "Keysight DSOX1204G"

    def screenshot(self) -> Image:
        self.write("HARDcopy:INKSaver 0")
        self.write("HARDcopy:SDUMp:DATA?")
        data = self.read_raw()
        return Image.open(io.BytesIO(data[int(data[1:2].decode()) + 2:]))
