from alembic import context
from app.config import Settings
from app.db.engine import make_engine
from app.db.models import metadata
from app.services.backup import create_backup, verify_backup

settings = Settings.from_env()
settings.prepare()
engine = make_engine(settings.db_path)
with engine.connect().execution_options(sqlite_begin="IMMEDIATE") as connection:
    context.configure(connection=connection, target_metadata=metadata, transactional_ddl=True)
    with context.begin_transaction():
        # Hold the writer lock while snapshotting the committed legacy database.
        exists = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE name='alembic_version'").first()
        if exists and connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version").scalar() == "0001":
            snapshot = create_backup(settings.db_path, settings.data_dir / "backups",
                                     expected_schema="0001")
            verify_backup(snapshot, expected_schema="0001")
        context.run_migrations()
engine.dispose()
