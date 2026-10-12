import sqlite3
from contextlib import closing
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from app.db.migrate import upgrade
from app.config import Settings
from app.services.backup import verify_backup


def dump(path):
    with closing(sqlite3.connect(path)) as c: return '\n'.join(c.iterdump())


@pytest.fixture
def gram_db(tmp_path,monkeypatch):
    monkeypatch.setenv('STORE_DATA_DIR',str(tmp_path/'grams'))
    command.upgrade(Config(str(Path(__file__).resolve().parents[1]/'alembic.ini')),'0002')
    path=Settings.from_env().db_path
    with closing(sqlite3.connect(path)) as c:
        with c:
            c.execute("INSERT INTO users VALUES(1,'synthetic','unused','manager',1)")
            c.execute("INSERT INTO documents VALUES('legacy','legacy','opening','posted','2026-01-01','now','now',1,0,'synthetic')")
            c.execute("INSERT INTO products VALUES(1,'s','name','name','count',1,1)")
            c.execute("INSERT INTO stock_balances VALUES(1,1,10,1)")
            c.execute("INSERT INTO document_lines VALUES('line','legacy',1,1,1,0,10,'{}')")
            c.execute("INSERT INTO stock_movements VALUES(1,1,'line',1,10,0,0,1,10,'now')")
            c.execute("INSERT INTO idempotency_records VALUES('legacy-command-1','hash','legacy',2)")
    return path


def test_upgrade_0002_preserves_existing_rows_backup_and_triggers(gram_db):
    before=dump(gram_db)
    upgrade()
    backup,=(gram_db.parent/'backups').glob('*.sqlite3')
    assert verify_backup(backup,expected_schema='0002')=='0002'
    assert dump(backup)==before
    with closing(sqlite3.connect(gram_db)) as c:
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert c.execute('SELECT * FROM idempotency_records').fetchone()==('legacy-command-1','hash','legacy',2)
        for table in ('documents','document_lines','stock_movements'):
            with pytest.raises(sqlite3.IntegrityError,match='Immutable'): c.execute(f'DELETE FROM {table}')
    after=dump(gram_db); upgrade(); assert dump(gram_db)==after


@pytest.mark.parametrize('failure',['CREATE TABLE payments','CREATE TRIGGER payments_no_delete'])
def test_rebuild_and_ledger_ddl_roll_back_and_retry(gram_db,failure):
    before=dump(gram_db)
    def fail(conn,cursor,statement,parameters,context,executemany):
        if failure in statement: raise RuntimeError('injected commerce migration failure')
    event.listen(Engine,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError,match='injected commerce'): upgrade()
    finally: event.remove(Engine,'before_cursor_execute',fail)
    assert dump(gram_db)==before
    upgrade()
