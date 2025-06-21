from importlib.resources import files

from jinja2 import Template

from workbench.datalogging import FromEnv
from workbench.datalogging.postgresql import PostgreSQLDatalogger


class TimescaleDBDatalogger(PostgreSQLDatalogger):
    _resources = files("workbench.datalogging.timescaledb")
    create_table = Template(_resources.joinpath("resources/create_table.sql.j2").read_text())

    def __init__(self, table: str, dsn: str | FromEnv = FromEnv("TIMESCALEDB_DSN")):
        super().__init__(table, dsn)


if __name__ == "__main__":
    with TimescaleDBDatalogger("test3") as datalogger:
        datalogger.log("test", 1.0, "test2")
