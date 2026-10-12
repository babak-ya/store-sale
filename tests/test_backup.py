import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.services.backup import create_backup, verify_backup, validate_snapshot
from app.services.catalog import create_product
from app.services.posting import post_stock


def test_backup_and_copy_restore(settings, engine, manager, tmp_path):
    pid = create_product(engine, actor_id=manager, sku="test", name="مصنوعی", kind="count", step=1, price=100, basis=1)
    post_stock(engine, actor_id=manager, key="synthetic-opening-key", kind="opening", product_id=pid,
               qty=3, value=100, reason="synthetic")
    snapshot = create_backup(settings.db_path, settings.data_dir / "backups")
    assert verify_backup(snapshot) == "0001"
    restored = tmp_path / "restore-test.sqlite3"
    with sqlite3.connect(snapshot) as source, sqlite3.connect(restored) as destination:
        source.backup(destination)
    assert validate_snapshot(restored) == "0001"
    with sqlite3.connect(restored) as c:
        assert c.execute("SELECT qty_base,value_rial FROM stock_balances").fetchone() == (3, 100)
        assert c.execute("SELECT SUM(qty_delta),SUM(value_delta) FROM stock_movements").fetchone() == (3, 100)
    info = json.loads(snapshot.with_suffix(".json").read_text())
    info["sha256"] = "0" * 64
    snapshot.with_suffix(".json").write_text(json.dumps(info))
    with pytest.raises(ValueError):
        verify_backup(snapshot)


def test_reject_corrupt_and_wrong_schema(tmp_path):
    bad = tmp_path / "bad.sqlite3"
    bad.write_bytes(b"invalid sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        validate_snapshot(bad)
    for schema in ("0000", "9999"):
        path = tmp_path / (schema + ".sqlite3")
        with sqlite3.connect(path) as c:
            c.execute("CREATE TABLE alembic_version(version_num TEXT)")
            c.execute("INSERT INTO alembic_version VALUES (?)", (schema,))
        with pytest.raises(ValueError):
            validate_snapshot(path)


def test_backup_during_posting(settings, engine, manager):
    pid = create_product(engine, actor_id=manager, sku="concurrent", name="مصنوعی", kind="count", step=1, price=100, basis=1)
    post_stock(engine, actor_id=manager, key="concurrent-opening-key", kind="opening", product_id=pid,
               qty=100, value=1000, reason="synthetic")
    def sell():
        for i in range(20):
            post_stock(engine, actor_id=manager, key=f"concurrent-sale-key-{i}", kind="sale", product_id=pid,
                       qty=1, price_version=1, reason="synthetic")
    with ThreadPoolExecutor(max_workers=2) as pool:
        posting = pool.submit(sell)
        snapshots = [create_backup(settings.db_path, settings.data_dir / "backups") for _ in range(3)]
        posting.result()
    for snapshot in snapshots:
        verify_backup(snapshot)
        with sqlite3.connect(snapshot) as c:
            assert c.execute("SELECT qty_base,value_rial FROM stock_balances").fetchone() == c.execute(
                "SELECT SUM(qty_delta),SUM(value_delta) FROM stock_movements").fetchone()
