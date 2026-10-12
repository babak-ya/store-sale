from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import select, insert, update, func
from sqlalchemy.exc import IntegrityError, OperationalError
from app.db import models as m
from app.db.engine import write_transaction
from app.domain.units import DomainError
from app.services.catalog import create_product
from app.services.posting import post_stock, Conflict


def product(engine, manager):
    return create_product(engine, actor_id=manager, sku="0001", name="زعفران آزمایشی",
                          kind="weight", step=1, price=150000, basis=1)


def opening(engine, manager, pid, **kw):
    return post_stock(engine, key=kw.pop("key", uuid4().hex), actor_id=manager,
                      kind="opening", product_id=pid, qty=8, value=800000, reason="synthetic", **kw)


def sale(engine, manager, pid, qty=1, **kw):
    return post_stock(engine, key=kw.pop("key", uuid4().hex), actor_id=manager,
                      kind="sale", product_id=pid, qty=qty, price_version=kw.pop("price_version", 1),
                      reason="synthetic valuation test", **kw)


def assert_ledger(engine):
    with engine.connect() as c:
        for balance in c.execute(select(m.balances)).mappings():
            totals = c.execute(select(func.sum(m.movements.c.qty_delta), func.sum(m.movements.c.value_delta))
                        .where(m.movements.c.product_id == balance["product_id"])).one()
            assert (balance["qty_base"], balance["value_rial"]) == tuple(x or 0 for x in totals)


def test_pragmas(engine):
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert c.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
        assert c.exec_driver_sql("PRAGMA synchronous").scalar() == 2
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"


def test_idempotency_and_snapshot(engine, manager):
    pid = product(engine, manager)
    key = uuid4().hex
    doc = opening(engine, manager, pid, key=key)
    assert opening(engine, manager, pid, key=key) == doc
    with pytest.raises(Conflict):
        sale(engine, manager, pid, key=key)
    sale_doc = sale(engine, manager, pid)
    with engine.connect() as c:
        line = c.execute(select(m.lines).where(m.lines.c.document_id == sale_doc)).mappings().one()
        assert (line["net_rial"], line["cost_rial"]) == (150000, 100000)
        assert c.execute(select(func.count()).select_from(m.movements)).scalar() == 2
    assert_ledger(engine)


def test_two_connections_last_stock(engine, manager):
    pid = product(engine, manager)
    opening(engine, manager, pid)
    def run(_):
        try:
            return sale(engine, manager, pid, qty=8)
        except DomainError:
            return "insufficient"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, range(2)))
    assert outcomes.count("insufficient") == 1
    assert_ledger(engine)
    with engine.connect() as c:
        row = c.execute(select(m.balances)).mappings().one()
        assert (row["qty_base"], row["value_rial"]) == (0, 0)


def test_concurrent_same_command(engine, manager):
    pid = product(engine, manager)
    opening(engine, manager, pid)
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: sale(engine, manager, pid, key=key), range(2)))
    assert results[0] == results[1]
    assert_ledger(engine)


def test_price_conflict_and_immutable_history(engine, manager):
    pid = product(engine, manager)
    opening(engine, manager, pid)
    with write_transaction(engine) as c:
        c.execute(insert(m.prices).values(product_id=pid, unit_price_rial=1300000, basis_qty=8,
                   version=2, changed_at="2026-01-01T00:00:00+00:00", changed_by=manager))
    with pytest.raises(Conflict):
        sale(engine, manager, pid)
    sale(engine, manager, pid, price_version=2)
    for table in (m.documents, m.lines, m.movements, m.prices, m.audit, m.idempotency):
        with pytest.raises(IntegrityError):
            with write_transaction(engine) as c:
                c.execute(table.delete())
    with pytest.raises(IntegrityError):
        with write_transaction(engine) as c:
            c.execute(update(m.products).values(kind="count"))
    assert_ledger(engine)


def test_failure_mid_transaction_rolls_back_every_effect(engine, manager):
    pid = product(engine, manager)
    opening(engine, manager, pid)
    with engine.begin() as c:
        c.exec_driver_sql("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT, 'Injected write failure'); END")
    key = uuid4().hex
    with pytest.raises(IntegrityError):
        sale(engine, manager, pid, key=key)
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(m.documents)).scalar() == 1
        assert not c.execute(select(m.idempotency).where(m.idempotency.c.key == key)).first()
    assert_ledger(engine)
    with engine.begin() as c:
        c.exec_driver_sql("DROP TRIGGER fail_audit")
    sale(engine, manager, pid, key=key)
    assert_ledger(engine)


def test_db_constraints_and_permissions(engine, manager):
    pid = product(engine, manager)
    for values in [dict(qty_base=0, value_rial=1), dict(qty_base=-1), dict(qty_base=1.25)]:
        with pytest.raises(IntegrityError):
            with write_transaction(engine) as c:
                c.execute(update(m.balances).values(**values))
    with pytest.raises(PermissionError):
        opening(engine, 999, pid)


def test_lock_failure_has_no_effect(engine, manager):
    pid = product(engine, manager)
    opening(engine, manager, pid)
    # Shorten only this test's connection timeout, preserving production 5000ms.
    with write_transaction(engine):
        with engine.connect() as contender:
            contender.connection.driver_connection.execute("PRAGMA busy_timeout=10")
            with pytest.raises(OperationalError):
                contender.execution_options(sqlite_begin="IMMEDIATE").begin()
    assert_ledger(engine)
