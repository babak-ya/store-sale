from pathlib import Path
from alembic import command
from alembic.config import Config


def upgrade():
    # CLI and launcher use the same migration directory, independently of cwd.
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    command.upgrade(config, "head")
