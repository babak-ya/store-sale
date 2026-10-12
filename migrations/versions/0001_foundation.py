"""Phase-zero immutable posting foundation."""
from alembic import op
from migrations.schema_0001 import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())
    for table in ("documents", "document_lines", "stock_movements", "prices", "audit_events", "idempotency_records"):
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                       "BEGIN SELECT RAISE(ABORT, 'Immutable ledger'); END")
    op.execute("CREATE TRIGGER product_kind_fixed BEFORE UPDATE OF kind, quantity_step ON products "
               "WHEN EXISTS (SELECT 1 FROM stock_movements WHERE product_id = OLD.id) "
               "BEGIN SELECT RAISE(ABORT, 'Unit immutable after movement'); END")


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup instead")
