from datetime import datetime, timezone
from importlib.resources import files
from typing import Optional

import numpy as np
import psycopg
from jinja2 import Template
from psycopg.rows import namedtuple_row

from workbench.datalogging import Datalogger, ValueType, FromEnv


class PostgreSQLDatalogger(Datalogger):
    _resources = files("workbench.datalogging.postgresql")
    create_table = Template(_resources.joinpath("resources/create_table.sql.j2").read_text())
    insert_into = Template(_resources.joinpath("resources/insert_into.sql.j2").read_text())
    select = Template(_resources.joinpath("resources/select.sql.j2").read_text())

    def __init__(self, table: str, dsn: str | FromEnv = FromEnv("POSTGRESQL_DSN")):
        self.dsn = self.get_config(dsn)
        self.table = table

    def __enter__(self):
        self.connection = psycopg.connect(self.dsn)
        self.connection.autocommit = True
        self.cursor = self.connection.cursor()
        self.cursor.execute(self.create_table.render(table=self.table))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()
        self.connection.close()

    def log(self, measurement: str, value: ValueType, experiment: str, *, timestamp: np.datetime64 = None):
        timestamp = timestamp or np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None))
        self.cursor.execute(self.insert_into.render(table=self.table), (
            timestamp.astype(datetime).replace(tzinfo=timezone.utc),
            measurement,
            value,
            experiment,
        ))

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
        with self.connection.cursor(row_factory=namedtuple_row) as cur:
            query = self.select.render(table=self.table)
            cur.execute(query, (start, stop, experiment))
            rows = cur.fetchall()

        dtype = [("time", "datetime64[ns]"), ("measurement", "U64"), ("value", "f8")]
        return self.pivot_measurements(
            np.array([(np.datetime64(r.time.replace(tzinfo=None)), r.measurement, r.value) for r in rows], dtype=dtype))
