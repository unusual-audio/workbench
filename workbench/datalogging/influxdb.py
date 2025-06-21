from datetime import datetime, timezone
from typing import Optional

import numpy as np
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from workbench.datalogging import Datalogger, FromEnv, ValueType


class InfluxDBDatalogger(Datalogger):

    def __init__(self, bucket: str, url: str = FromEnv("INFLUXDB_URL"), org: str = FromEnv("INFLUXDB_ORG"),
                 token: str = FromEnv("INFLUXDB_TOKEN")):
        self.bucket = bucket
        self.org = self.get_config(org)
        self.token = self.get_config(token)
        self.url = self.get_config(url)

    def __enter__(self):
        self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
        self.query_api = self.client.query_api()
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.write_api.close()
        self.client.close()

    def log(self, measurement: str, value: ValueType, experiment: str, *, timestamp: np.datetime64 = None):
        timestamp = timestamp or np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None))
        point = (
            Point(measurement)
            .field("value", float(value))
            .tag("experiment", experiment)
            .time(timestamp.astype(datetime).replace(tzinfo=timezone.utc)))
        self.write_api.write(bucket=self.bucket, org=self.org, record=point)

    def query(
            self,
            time_from: np.datetime64,
            time_to: Optional[np.datetime64] = None,
            *,
            experiment: str,
    ) -> np.ndarray:
        time_to = time_to or np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None)) + np.timedelta64(1, "s")
        start = time_from.astype(datetime).replace(tzinfo=timezone.utc).isoformat()
        stop = time_to.astype(datetime).replace(tzinfo=timezone.utc).isoformat()
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start}, stop: {stop})
            |> filter(fn: (r) => r["_measurement"] != "" and r["experiment"] == "{experiment}")
            |> filter(fn: (r) => r["_field"] == "value")
            |> keep(columns: ["_time", "_measurement", "_value"])
        '''

        tables = self.query_api.query(query=query, org=self.org)
        results = []

        for table in tables:
            for record in table.records:
                results.append((
                    np.datetime64(record.get_time().replace(tzinfo=None)),
                    record.get_measurement(),
                    record.get_value(),
                ))

        dtype = [("time", "datetime64[ns]"), ("measurement", "U64"), ("value", "f8")]
        return self.pivot_measurements(np.array(np.array(results, dtype=dtype)))
