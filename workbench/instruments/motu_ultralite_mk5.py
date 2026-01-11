import sounddevice as sd

from workbench.instruments.audio import AudioInterface, WaveformType


class MOTOUltraLiteMk5(AudioInterface):
    pass


if __name__ == "__main__":
    with MOTOUltraLiteMk5.connect() as motu_ultralite_mk5:
        motu_ultralite_mk5.set_waveform(3, WaveformType.SINE)
        motu_ultralite_mk5.set_frequency(3, 440.0)
        motu_ultralite_mk5.set_amplitude(3, 0.5)
        motu_ultralite_mk5.enable_output(3)
        sd.sleep(1000)