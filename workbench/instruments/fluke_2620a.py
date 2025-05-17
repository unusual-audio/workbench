import datetime

from workbench.instruments import SerialInstrument


class Fluke2620A(SerialInstrument):

    instrument_name = "Fluke 2620A"

    @property
    def identity(self) -> str:
        self.write("*IDN?")
        result = self.read()
        assert (r := self.read()).strip() == "=>", repr(r)
        return result

    def single(self) -> (datetime.datetime, tuple[float]):
        self.query("*TRG")
        response = self.query_ascii_values("NEXT?", converter="s")
        hour, minute, second, month, day, year, *values, alarms, dio, total = response
        date = datetime.datetime(2000 + int(year), int(month), int(day), int(hour), int(minute), int(second))
        assert (r := self.read()).strip() == "=>", repr(r)
        return date, values
