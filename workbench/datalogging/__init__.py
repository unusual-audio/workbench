from __future__ import annotations

import copy
import datetime
import logging
import time
import typing

import dotenv
import numpy as np
from influxdb_client import InfluxDBClient, WriteApi, QueryApi


class Datalogger:

    def __init__(self, influxdb_client: InfluxDBClient, *, logger: logging.Logger = None, **default_tags: object):
        self.influxdb_client = influxdb_client
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.default_tags = default_tags
        self.influxdb_write_api: typing.Optional[WriteApi] = None
        self.influxdb_query_api: typing.Optional[QueryApi] = self.influxdb_client.query_api()

    def write(self, measurement: str, reading: object, timestamp: datetime.datetime = None, **tags: dict[str, object]):
        timestamp = timestamp or self.get_timestamp()
        self.logger.info(f"{measurement} = {reading}")
        record = {
            "measurement": measurement,
            "tags": copy.deepcopy(self.default_tags) | tags,
            "fields": {
                "reading": reading,
            },
            "time": timestamp,
        }
        self.influxdb_write_api.write("measurements", record=record)

    @staticmethod
    def get_timestamp() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    def __enter__(self) -> Datalogger:
        if self.influxdb_write_api is None:
            self.influxdb_write_api = self.influxdb_client.write_api()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.influxdb_write_api.close()
        self.influxdb_write_api = None

    def run_forever(self, function: typing.Callable[[Datalogger], None], retry: bool = True):
        with self:
            timeout = 60
            while True:
                try:
                    function(self)
                except KeyboardInterrupt:
                    break
                except Exception:
                    self.logger.exception(f"Retrying in {timeout} seconds...")
                    time.sleep(timeout)
                else:
                    break

    @classmethod
    def from_env_properties(cls, *, debug=None, enable_gzip=False, logger: logging.Logger = None,
                            **default_tags: object):
        influxdb_client = InfluxDBClient.from_env_properties(debug=debug, enable_gzip=enable_gzip)
        return cls(influxdb_client=influxdb_client, logger=logger, **default_tags)

    @classmethod
    def interactive(cls, experiment: typing.Optional[str], debug=False, **default_tags):
        dotenv.load_dotenv()
        logging.basicConfig(
            format="[%(asctime)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S%z",
            level=(logging.DEBUG if debug else logging.INFO))
        default_tags = default_tags
        if experiment is not None:
            default_tags["experiment"] = experiment
        return cls.from_env_properties(debug=debug, **default_tags)

    def load_experiment_data(self, start, dtype):
        stream = self.influxdb_query_api.query_stream(f"""
            import "date"
            from(bucket: "measurements")
              |> range(start: {start})
              |> filter(fn: (r) => r["experiment"] == "{self.default_tags['experiment']}")
              |> pivot(rowKey: ["_time"], columnKey: ["_measurement"], valueColumn: "_value")
              |> rename(columns: {{_time: "timestamp"}})
              """)
        t = lambda x: x.astimezone(datetime.timezone.utc).replace(tzinfo=None) if isinstance(x,
                                                                                             datetime.datetime) else x
        return np.array([tuple(t(i[k]) for k, _ in dtype) for i in stream if all(i[k] is not None for k, _ in dtype)],
                        dtype=dtype)


if __name__ == "__main__":
    with Datalogger.interactive(experiment=None, debug=True) as datalogger:
        datalogger.write("test_value", 100.0)
