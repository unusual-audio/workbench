import io

from PIL import Image

from workbench.instruments import VisaInstrument


class KeysightDSOX1204G(VisaInstrument):
    instrument_name = "Keysight DSOX1204G"

    def screenshot(self, invert=False, crop_header=True) -> Image.Image:
        self.write(f"HARDcopy:INKSaver {'1' if invert else '0'}")
        self.write("HARDcopy:SDUMp:DATA?")
        data = self.read_raw()
        i = Image.open(io.BytesIO(data[int(data[1:2].decode()) + 2:]))
        if crop_header:
            i = i.crop((0, 23, i.width, i.height))
        return i
