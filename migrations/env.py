from alembic import context
from app.config import Settings
from app.db.engine import make_engine
from app.db.models import metadata

settings = Settings.from_env()
settings.prepare()
engine = make_engine(settings.db_path)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata, transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
