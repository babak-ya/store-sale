"""Consistent local snapshots. Production restore is deliberately not exposed yet."""
from contextlib import closing
import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4
from app import __version__
from app.domain.clock import now_utc


def validate_snapshot(path, expected_schema="0003"):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as c:
        if c.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Backup integrity check failed")
        if c.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Backup foreign key check failed")
        row = c.execute("SELECT version_num FROM alembic_version").fetchone()
        if not row or row[0] != expected_schema:
            raise ValueError("Unsupported backup schema")
        return row[0]


def create_backup(db_path, destination, *, expected_schema="0003"):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    at = now_utc()
    name = at.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex
    tmp = destination / (name + ".tmp")
    final = destination / (name + ".sqlite3")
    manifest = destination / (name + ".json")
    try:
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(tmp)) as target:
                source.backup(target)
        schema = validate_snapshot(tmp, expected_schema)
        digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
        size = tmp.stat().st_size
        tmp.replace(final)
        manifest.write_text(json.dumps(dict(app_version=__version__, schema_version=schema,
            created_at=at.isoformat(), size_bytes=size, sha256=digest, file=final.name), indent=2), encoding="utf-8")
        return final
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def verify_backup(path, *, expected_schema="0003"):
    path = Path(path)
    info = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if info["file"] != path.name or info["size_bytes"] != path.stat().st_size:
        raise ValueError("Backup manifest mismatch")
    if info["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError("Backup checksum mismatch")
    return validate_snapshot(path, expected_schema)
