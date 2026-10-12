"""Upgrade real schema-0001 files containing synthetic stock and immutable history."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from app.config import Settings
from app.db.engine import make_engine
from app.db.migrate import upgrade
from app.services.backup import verify_backup
from app.services.posting import post_stock, Conflict
from app.web.application import create_app


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("STORE_DATA_DIR", str(tmp_path / "legacy"))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0001")
    path = Settings.from_env().db_path
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO users VALUES (1,'synthetic','unused','manager',1)")
        for pid, kind, step, basis, qty in [(1, 'weight', 1000, 1000, 8000), (2, 'count', 1, 1, 8)]:
            c.execute("INSERT INTO products VALUES (?,?,?,?,?,?,1)", (pid, str(pid), kind, kind, kind, step))
            c.execute("INSERT INTO prices VALUES (?,?,150000,?,1,'2026-01-01',1)", (pid, pid, basis))
            c.execute("INSERT INTO stock_balances VALUES (?,?,700000,2)", (pid, qty - step))
            for kind, q, before, after, vb, va, net, cost in [
                    ('opening', qty, 0, qty, 0, 800000, 0, 800000),
                    ('sale', step, qty, qty-step, 800000, 700000, 150000, 100000)]:
                doc = f'{pid}-{kind}'
                c.execute("INSERT INTO documents VALUES (?,?,?,'posted','2026-01-01','now','now',1,?,'synthetic')", (doc, doc, kind, net))
                snapshot = dict(name='synthetic', kind='weight' if pid == 1 else 'count', quantity_step=step, discount_rial=0)
                if kind == 'sale':
                    snapshot.update(unit_price_rial=150000, basis_qty=basis, price_version=1)
                c.execute("INSERT INTO document_lines VALUES (?,?,1,?,?,?,?,?)", (doc, doc, pid, q, net, cost, json.dumps(snapshot)))
                c.execute("INSERT INTO stock_movements (product_id,document_line_id,qty_delta,value_delta,quantity_before,value_before,quantity_after,value_after,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (pid, doc, q if kind=='opening' else -q, cost if kind=='opening' else -cost, before, vb, after, va, 'now'))
                payload = dict(actor_id=1, kind=kind, product_id=pid, qty=q, reason='synthetic', value=800000 if kind=='opening' else 0, price_version=1 if kind=='sale' else None, discount=0)
                digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                c.execute("INSERT INTO idempotency_records VALUES (?,?,?)", (f'legacy-command-{doc}', digest, doc))
    return path


def dump(path):
    with sqlite3.connect(path) as c:
        return '\n'.join(c.iterdump())


def test_exact_upgrade_preserves_money_history_retries_and_backup(legacy):
    original = dump(legacy)
    upgrade()
    with sqlite3.connect(legacy) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ('0002',)
        assert c.execute("SELECT quantity_step FROM products ORDER BY id").fetchall() == [(1,), (1,)]
        assert c.execute("SELECT basis_qty,unit_price_rial FROM prices").fetchall() == [(1,150000), (1,150000)]
        assert c.execute("SELECT qty_base,value_rial FROM stock_balances").fetchall() == [(7,700000), (7,700000)]
        assert c.execute("SELECT qty_delta,quantity_before,quantity_after,value_delta FROM stock_movements WHERE product_id=1").fetchall() == [(8,0,8,800000),(-1,8,7,-100000)]
        for qty, net, cost, raw in c.execute("SELECT qty_base,net_rial,cost_rial,snapshot_json FROM document_lines WHERE product_id=1"):
            snapshot = json.loads(raw)
            assert snapshot['quantity_step'] == 1 and snapshot['quantity_unit'] == 'g'
            if 'basis_qty' in snapshot:
                assert (qty,net,cost,snapshot['basis_qty']) == (1,150000,100000,1)
        assert c.execute("PRAGMA integrity_check").fetchall() == [('ok',)]
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in ['document_lines','stock_movements','prices','idempotency_records','documents','audit_events']:
            with pytest.raises(sqlite3.IntegrityError, match='Immutable'):
                c.execute(f"DELETE FROM {table}" if table != 'audit_events' else "UPDATE prices SET basis_qty=2")
        with pytest.raises(sqlite3.IntegrityError, match='Unit immutable'):
            c.execute("UPDATE products SET quantity_step=2")
    backup, = (legacy.parent / 'backups').glob('*.sqlite3')
    assert verify_backup(backup, expected_schema='0001') == '0001'
    assert dump(backup) == original
    engine = make_engine(legacy)
    try:
        for pid in (1,2):
            for kind, qty in [('opening',8),('sale',1)]:
                kwargs = dict(engine=engine, actor_id=1, key=f'legacy-command-{pid}-{kind}', kind=kind, product_id=pid, qty=qty, reason='synthetic', value=800000 if kind=='opening' else 0, price_version=1 if kind=='sale' else None)
                assert post_stock(**kwargs) == f'{pid}-{kind}'
                with pytest.raises(Conflict):
                    post_stock(**(kwargs | {'qty':qty+1}))
        post_stock(engine, actor_id=1, key='new-gram-sale-command', kind='sale', product_id=1, qty=7, price_version=1, reason='synthetic')
        with engine.connect() as c:
            assert c.exec_driver_sql("SELECT qty_base,value_rial FROM stock_balances WHERE product_id=1").one() == (0,0)
            assert c.exec_driver_sql("SELECT net_rial,cost_rial FROM document_lines WHERE qty_base=7").one() == (1050000,700000)
    finally:
        engine.dispose()
    before = dump(legacy)
    upgrade()
    assert dump(legacy) == before


@pytest.mark.parametrize('table,column,value', [
    ('products','quantity_step',125), ('prices','basis_qty',125),
    ('stock_balances','qty_base',7001), ('document_lines','qty_base',1001),
    ('stock_movements','qty_delta',-999), ('stock_movements','quantity_before',8001),
    ('stock_movements','quantity_after',7001),
    ('document_lines','snapshot_json', '{"kind":"weight","quantity_step":125}'),
    ('document_lines','snapshot_json', '{"kind":"weight","quantity_step":1000,"basis_qty":125}'),
    ('document_lines','snapshot_json', 'not JSON'),
])
def test_inexact_history_blocks_without_changing_any_data(legacy, table, column, value):
    with sqlite3.connect(legacy) as c:
        triggers = c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
        for name, _ in triggers:
            c.execute(f'DROP TRIGGER {name}')
        owner = 'id' if table == 'products' else 'product_id'
        c.execute(f'UPDATE {table} SET {column}=? WHERE {owner}=1', (value,))
        for _, sql in triggers:
            c.execute(sql)
    before = dump(legacy)
    with pytest.raises(RuntimeError, match='Whole-gram upgrade blocked') as error:
        upgrade()
    assert table in str(error.value) and 'GRAM_MIGRATION.md' in str(error.value)
    assert dump(legacy) == before
    backup, = (legacy.parent / 'backups').glob('*.sqlite3')
    assert dump(backup) == before


def test_legacy_database_cannot_be_opened_as_grams(legacy):
    with pytest.raises(RuntimeError, match='Schema 0002'):
        create_app(Settings.from_env())


def test_failure_after_conversion_rolls_back_ddl_data_and_guards(legacy):
    from sqlalchemy.engine import Engine
    before = dump(legacy)
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('ALTER TABLE idempotency_records'):
            raise RuntimeError('injected late migration failure')
    event.listen(Engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected late'):
            upgrade()
    finally:
        event.remove(Engine, 'before_cursor_execute', fail)
    assert dump(legacy) == before
    upgrade()


def test_backup_failure_prevents_migration_writes(legacy, monkeypatch):
    from app.services import backup
    before = dump(legacy)
    def fail(*args, **kwargs):
        raise OSError('synthetic backup failure')
    monkeypatch.setattr(backup, 'create_backup', fail)
    with pytest.raises(OSError, match='synthetic backup failure'):
        upgrade()
    assert dump(legacy) == before
