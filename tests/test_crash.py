"""Abrupt-process-exit tests against a real file, not an in-memory transaction."""
import os
import subprocess
import sys
from uuid import uuid4
from sqlalchemy import select, func
from app.db import models as m
from app.services.posting import post_stock
from test_posting import product, opening, assert_ledger


def test_process_crash_before_and_after_commit(engine, manager, settings):
    pid = product(engine, manager)
    opening(engine, manager, pid)
    key = uuid4().hex
    script = '''
import os, sys
from sqlalchemy import event
from app.db.engine import make_engine
from app.services.posting import post_stock
engine = make_engine(sys.argv[1])
if sys.argv[5] == "before":
    @event.listens_for(engine, "before_cursor_execute")
    def interrupt(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            os._exit(71)
post_stock(engine, key=sys.argv[4], actor_id=int(sys.argv[2]), kind="sale",
           product_id=int(sys.argv[3]), qty=125, price_version=1, reason="crash-test")
os._exit(72)
'''
    for mode, exit_code in [("before", 71), ("after", 72)]:
        result = subprocess.run([sys.executable, "-c", script, str(settings.db_path), str(manager), str(pid), key, mode],
                                env=os.environ.copy(), timeout=20)
        assert result.returncode == exit_code
        assert_ledger(engine)
        with engine.connect() as c:
            count = c.execute(select(func.count()).select_from(m.documents)).scalar()
            assert count == (1 if mode == "before" else 2)
    # Simulate losing the HTTP response after commit; exact replay returns original.
    with engine.connect() as c:
        committed = c.execute(select(m.idempotency.c.result_id).where(m.idempotency.c.key == key)).scalar_one()
    assert post_stock(engine, key=key, actor_id=manager, kind="sale", product_id=pid,
                      qty=125, price_version=1, reason="crash-test") == committed
    assert_ledger(engine)
