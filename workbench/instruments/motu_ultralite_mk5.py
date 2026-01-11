import logging

from workbench.instruments import VisaInstrument
from workbench.instruments.audio import AudioInterface, ScpiSignalGenerator
from workbench.utils.server import ScpiServer


class MOTOUltraLiteMk5(VisaInstrument):

    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    with AudioInterface.connect("UltraLite-mk5") as audio_interface:
        ScpiServer(ScpiSignalGenerator(audio_interface=audio_interface, identity="MOTU,UltraLite-mk5,0,0")).start()
