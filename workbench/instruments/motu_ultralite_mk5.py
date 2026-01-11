from typing import Self, Optional

import sounddevice as sd

from workbench.instruments.audio import AudioInterface, WaveformType, ChannelConfig
from workbench.utils import dbu_to_vrms


class MOTOUltraLiteMk5(AudioInterface):

    def get_default_channel_config(self, channel: Optional[int] = None) -> ChannelConfig:
        config = ChannelConfig(sample_rate=self.sample_rate)
        if channel in (0, 1, 2, 3, 4, 5, 6, 7):
            config.calibration_vrms_at_fs = dbu_to_vrms(+21)  # from the manual
        return config

    @classmethod
    def connect(cls, address: str = "UltraLite-mk5") -> Self:
        return super(MOTOUltraLiteMk5, cls).connect(address)
