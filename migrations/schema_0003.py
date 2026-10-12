from sqlalchemy import (MetaData, Table, Column, Integer, Text, ForeignKey,
                        CheckConstraint, UniqueConstraint)

# Schema 0002: weight quantities/bases/steps are integer grams; counts are items.
# All monetary columns remain integer rial. Historical schema 0001 is frozen.
metadata = MetaData()

users = Table("users", metadata,
    Column("id", Integer, primary_key=True), Column("username", Text, nullable=False, unique=True),
    Column("password_hash", Text, nullable=False), Column("role", Text, nullable=False),
    Column("active", Integer, nullable=False, server_default="1"),
    CheckConstraint("role IN ('manager','cashier')"), CheckConstraint("active IN (0,1)"))
sessions = Table("sessions", metadata,
    Column("token_hash", Text, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("expires_at", Text, nullable=False))
products = Table("products", metadata,
    Column("id", Integer, primary_key=True), Column("sku", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False), Column("normalized_name", Text, nullable=False, index=True),
    Column("kind", Text, nullable=False), Column("quantity_step", Integer, nullable=False),
    Column("active", Integer, nullable=False, server_default="1"),
    CheckConstraint("kind IN ('weight','count')"), CheckConstraint("active IN (0,1)"),
    CheckConstraint("typeof(quantity_step) = 'integer' AND quantity_step > 0"))
prices = Table("prices", metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True),
    Column("unit_price_rial", Integer, nullable=False), Column("basis_qty", Integer, nullable=False),
    Column("version", Integer, nullable=False), Column("changed_at", Text, nullable=False),
    Column("changed_by", Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    UniqueConstraint("product_id", "version"),
    CheckConstraint("typeof(unit_price_rial) = 'integer' AND unit_price_rial >= 0"),
    CheckConstraint("typeof(basis_qty) = 'integer' AND basis_qty > 0"))
balances = Table("stock_balances", metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True),
    Column("qty_base", Integer, nullable=False, server_default="0"),
    Column("value_rial", Integer, nullable=False, server_default="0"),
    Column("version", Integer, nullable=False, server_default="0"),
    CheckConstraint("typeof(qty_base) = 'integer' AND qty_base >= 0"),
    CheckConstraint("typeof(value_rial) = 'integer' AND value_rial >= 0"),
    CheckConstraint("qty_base != 0 OR value_rial = 0"))
documents = Table("documents", metadata,
    Column("id", Text, primary_key=True), Column("number", Text, unique=True, nullable=False),
    Column("kind", Text, nullable=False), Column("status", Text, nullable=False),
    Column("accounting_date", Text, nullable=False, index=True),
    Column("created_at", Text, nullable=False), Column("posted_at", Text, nullable=False),
    Column("actor_id", Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("net_rial", Integer, nullable=False), Column("reason", Text, nullable=False),
    CheckConstraint("kind IN ('opening','sale','purchase','supplier_payment')"), CheckConstraint("status = 'posted'"),
    CheckConstraint("typeof(net_rial) = 'integer' AND net_rial >= 0"))
lines = Table("document_lines", metadata,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True),
    Column("line_no", Integer, nullable=False),
    Column("product_id", Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
    Column("qty_base", Integer, nullable=False), Column("net_rial", Integer, nullable=False),
    Column("cost_rial", Integer, nullable=False), Column("snapshot_json", Text, nullable=False),
    UniqueConstraint("document_id", "line_no"),
    CheckConstraint("typeof(qty_base) = 'integer' AND qty_base > 0"),
    CheckConstraint("typeof(net_rial) = 'integer' AND net_rial >= 0"),
    CheckConstraint("typeof(cost_rial) = 'integer' AND cost_rial >= 0"))
movements = Table("stock_movements", metadata,
    Column("sequence", Integer, primary_key=True),
    Column("product_id", Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True),
    Column("document_line_id", Text, ForeignKey("document_lines.id", ondelete="RESTRICT"), nullable=False, unique=True),
    Column("qty_delta", Integer, nullable=False), Column("value_delta", Integer, nullable=False),
    Column("quantity_before", Integer, nullable=False), Column("value_before", Integer, nullable=False),
    Column("quantity_after", Integer, nullable=False), Column("value_after", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    CheckConstraint("typeof(qty_delta) = 'integer' AND typeof(value_delta) = 'integer'"),
    CheckConstraint("quantity_after >= 0 AND value_after >= 0"),
    CheckConstraint("quantity_after != 0 OR value_after = 0"))
idempotency = Table("idempotency_records", metadata,
    Column("key", Text, primary_key=True), Column("payload_hash", Text, nullable=False),
    Column("result_id", Text, ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False),
    Column("quantity_version", Integer, nullable=False, server_default="1"),
    CheckConstraint("quantity_version IN (1,2)"))
audit = Table("audit_events", metadata,
    Column("id", Integer, primary_key=True),
    Column("actor_id", Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("action", Text, nullable=False), Column("reference", Text, nullable=False),
    Column("reason", Text, nullable=False), Column("created_at", Text, nullable=False))

# Minimal commerce ledgers. Posted records are protected by database triggers.
suppliers = Table("suppliers", metadata,
    Column("id", Integer, primary_key=True), Column("name", Text, nullable=False, unique=True),
    Column("phone", Text, nullable=False), Column("created_by", Integer, ForeignKey("users.id"), nullable=False))
purchases = Table("purchases", metadata,
    Column("document_id", Text, ForeignKey("documents.id"), primary_key=True),
    Column("supplier_id", Integer, ForeignKey("suppliers.id"), nullable=False, index=True),
    Column("supplier_name", Text, nullable=False))
payments = Table("payments", metadata,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, ForeignKey("documents.id"), nullable=False, unique=True),
    Column("purchase_id", Text, ForeignKey("purchases.document_id"), nullable=True, index=True),
    Column("direction", Text, nullable=False), Column("method", Text, nullable=False),
    Column("amount_rial", Integer, nullable=False), Column("tendered_rial", Integer, nullable=False),
    Column("change_rial", Integer, nullable=False), Column("status", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    CheckConstraint("direction IN ('in','out')"),
    CheckConstraint("method IN ('cash','manual_card','external_transfer')"),
    CheckConstraint("status IN ('confirmed_cash','confirmed_manual')"),
    CheckConstraint("typeof(amount_rial)='integer' AND amount_rial>0"),
    CheckConstraint("typeof(tendered_rial)='integer' AND tendered_rial>=amount_rial"),
    CheckConstraint("typeof(change_rial)='integer' AND change_rial=tendered_rial-amount_rial"))
payables = Table("supplier_entries", metadata,
    Column("id", Integer, primary_key=True),
    Column("supplier_id", Integer, ForeignKey("suppliers.id"), nullable=False, index=True),
    Column("purchase_id", Text, ForeignKey("purchases.document_id"), nullable=False, index=True),
    Column("document_id", Text, ForeignKey("documents.id"), nullable=False),
    Column("event", Text, nullable=False), Column("amount_rial", Integer, nullable=False),
    UniqueConstraint("document_id", "event"),
    CheckConstraint("event IN ('purchase','payment')"),
    CheckConstraint("typeof(amount_rial)='integer' AND ((event='purchase' AND amount_rial>0) OR (event='payment' AND amount_rial<0))"))
counters = Table("document_counters", metadata,
    Column("kind", Text, primary_key=True), Column("value", Integer, nullable=False),
    CheckConstraint("typeof(value)='integer' AND value>0"))
carts = Table("carts", metadata,
    Column("id", Text, primary_key=True), Column("actor_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("kind", Text, nullable=False), Column("version", Integer, nullable=False),
    Column("items_json", Text, nullable=False),
    Column("posted_id", Text, ForeignKey("documents.id"), nullable=True),
    CheckConstraint("kind IN ('sale','purchase')"))
