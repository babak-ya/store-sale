"""Convert every persisted weight quantity exactly from milligrams to grams."""
import json
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Frozen schema-0001 quantity locations. Never import the evolving application model.
FIELDS = {
    "products": ("id", ("quantity_step",)),
    "prices": ("id", ("basis_qty",)),
    "stock_balances": ("product_id", ("qty_base",)),
    "document_lines": ("id", ("qty_base",)),
    "stock_movements": ("sequence", ("qty_delta", "quantity_before", "quantity_after")),
}


def fail(location, value):
    raise RuntimeError(
        f"Whole-gram upgrade blocked: {location}={value!r} is not an exact supported "
        "milligram quantity/snapshot. No quantities were rounded. The transaction is "
        "rolled back to schema 0001. Keep the verified pre-upgrade backup; use the old "
        "application for this data and see docs/GRAM_MIGRATION.md. Do not edit history "
        "or stamp the new schema version.")


def grams(value, location, *, minimum=0):
    if type(value) is not int or value < minimum or value % 1000:
        fail(location, value)
    return value // 1000


def upgrade():
    c = op.get_bind()
    snapshots = []
    # Preflight the complete history, not just current balances, before any writes.
    for table, (key, columns) in FIELDS.items():
        owner = "id" if table == "products" else "product_id"
        rows = c.exec_driver_sql(
            f"SELECT * FROM {table} WHERE {owner} IN (SELECT id FROM products WHERE kind='weight')"
        ).mappings()
        for row in rows:
            for column in columns:
                minimum = -(2**63 - 1) if column == "qty_delta" else (
                    1 if column in {"quantity_step", "basis_qty"} or table == "document_lines" else 0)
                grams(row[column], f"{table}[{row[key]}].{column}", minimum=minimum)
            if table == "document_lines":
                location = f"document_lines[{row[key]}].snapshot_json"
                try:
                    snapshot = json.loads(row["snapshot_json"])
                except (ValueError, TypeError):
                    fail(location, "invalid JSON")
                if not isinstance(snapshot, dict) or snapshot.get("kind") != "weight":
                    fail(location, "missing or inconsistent kind")
                snapshot["quantity_step"] = grams(snapshot.get("quantity_step"), location + ".quantity_step", minimum=1)
                kind = c.exec_driver_sql("SELECT kind FROM documents WHERE id=?", (row["document_id"],)).scalar()
                if kind == "sale" or "basis_qty" in snapshot:
                    snapshot["basis_qty"] = grams(snapshot.get("basis_qty"), location + ".basis_qty", minimum=1)
                if "quantity_unit" in snapshot:
                    fail(location, "unexpected legacy unit marker")
                snapshot["quantity_unit"] = "g"
                snapshots.append((json.dumps(snapshot, ensure_ascii=False), row[key]))

    # SQLite DDL and data changes are inside the explicit Alembic transaction.
    # Temporarily remove only the guards that block the exact unit conversion.
    names = ["product_kind_fixed", "prices_no_update", "document_lines_no_update", "stock_movements_no_update"]
    triggers = []
    for name in names:
        sql = c.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).scalar()
        if not sql:
            fail("trigger", name)
        triggers.append(sql)
        c.exec_driver_sql(f"DROP TRIGGER {name}")
    for table, (_, columns) in FIELDS.items():
        owner = "id" if table == "products" else "product_id"
        assignments = ", ".join(f"{column}={column}/1000" for column in columns)
        c.exec_driver_sql(f"UPDATE {table} SET {assignments} WHERE {owner} IN "
                         "(SELECT id FROM products WHERE kind='weight')")
    for snapshot, line_id in snapshots:
        c.exec_driver_sql("UPDATE document_lines SET snapshot_json=? WHERE id=?", (snapshot, line_id))
    for sql in triggers:
        c.exec_driver_sql(sql)
    # Hashes remain byte-for-byte intact. Version 1 retries reconstruct mg payloads.
    c.exec_driver_sql("ALTER TABLE idempotency_records ADD COLUMN quantity_version INTEGER "
                     "NOT NULL DEFAULT 1 CHECK (quantity_version IN (1,2))")
    if c.exec_driver_sql("PRAGMA foreign_key_check").all():
        raise RuntimeError("Whole-gram migration failed foreign-key validation")


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup with the old application")
