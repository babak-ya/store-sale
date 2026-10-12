from alembic import context
from app.config import Settings
from app.db.engine import make_engine
from app.db.models import metadata
from app.services.backup import create_backup, verify_backup

settings = Settings.from_env()
settings.prepare()
engine = make_engine(settings.db_path)
try:
    with engine.connect().execution_options(sqlite_begin="IMMEDIATE") as connection:
        # SQLite requires FK enforcement off *before* BEGIN when rebuilding a
        # referenced table. This applies only to the migration connection. The
        # full database is checked inside the transaction before committing.
        raw = connection.connection.driver_connection
        raw.execute('PRAGMA foreign_keys=OFF')
        try:
            context.configure(connection=connection, target_metadata=metadata, transactional_ddl=True)
            with context.begin_transaction():
                exists = connection.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").first()
                previous = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() if exists else None
                if previous in {'0001', '0002'}:
                    snapshot = create_backup(settings.db_path, settings.data_dir / 'backups', expected_schema=previous)
                    verify_backup(snapshot, expected_schema=previous)
                context.run_migrations()
                if connection.exec_driver_sql('PRAGMA foreign_key_check').all():
                    raise RuntimeError('Migration foreign-key validation failed; all changes rolled back')
        finally:
            raw.execute('PRAGMA foreign_keys=ON')
finally:
    engine.dispose()
