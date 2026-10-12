"""Cashier checkout, purchases and minimal supplier settlement ledgers."""
from alembic import op
from sqlalchemy import MetaData
from migrations.schema_0003 import metadata

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    # Rebuild only the document header to widen its kind CHECK. Keep child FKs
    # checked inside the explicit transaction and restore all immutable guards.
    replacement = metadata.tables['documents'].to_metadata(MetaData(), name='documents_new')
    # Resolve the users FK in the temporary metadata without recreating users.
    metadata.tables['users'].to_metadata(replacement.metadata)
    replacement.create(c)
    c.exec_driver_sql("INSERT INTO documents_new SELECT * FROM documents")
    c.exec_driver_sql("DROP TABLE documents")
    c.exec_driver_sql("ALTER TABLE documents_new RENAME TO documents")
    for name in ('suppliers', 'purchases', 'payments', 'supplier_entries', 'document_counters', 'carts'):
        metadata.tables[name].create(c)
    for table in ('documents', 'purchases', 'payments', 'supplier_entries'):
        for action in ('UPDATE', 'DELETE'):
            c.exec_driver_sql(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                             "BEGIN SELECT RAISE(ABORT, 'Immutable ledger'); END")
    if c.exec_driver_sql('PRAGMA foreign_key_check').all():
        raise RuntimeError('Commerce migration failed foreign-key validation')


def downgrade():
    raise RuntimeError('Destructive downgrade is unsupported; restore a validated backup with the matching application')
