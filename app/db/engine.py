from contextlib import contextmanager
from sqlalchemy import create_engine, event


def make_engine(path):
    engine = create_engine("sqlite:///" + str(path), connect_args={"timeout": 5})

    @event.listens_for(engine, "connect")
    def configure(dbapi, _):
        # Disable sqlite3's implicit transaction handling; issue BEGIN explicitly.
        dbapi.isolation_level = None
        dbapi.execute("PRAGMA foreign_keys=ON")
        dbapi.execute("PRAGMA busy_timeout=5000")
        dbapi.execute("PRAGMA synchronous=FULL")

    @event.listens_for(engine, "begin")
    def begin(connection):
        mode = connection.get_execution_options().get("sqlite_begin", "DEFERRED")
        if mode not in {"DEFERRED", "IMMEDIATE"}:
            raise ValueError("Invalid transaction mode")
        connection.exec_driver_sql("BEGIN " + mode)

    with engine.connect() as c:
        mode = c.connection.driver_connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if mode != "wal":
            raise RuntimeError("SQLite WAL could not be enabled")
    return engine


@contextmanager
def write_transaction(engine):
    with engine.connect().execution_options(sqlite_begin="IMMEDIATE") as c:
        with c.begin():
            yield c
