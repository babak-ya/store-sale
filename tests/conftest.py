import pytest
from app.db.migrate import upgrade
from app.config import Settings
from app.db.engine import make_engine
from app.services.auth import create_first_manager


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("STORE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORE_PORT", "8765")
    upgrade()
    return Settings.from_env()


@pytest.fixture
def engine(settings):
    engine = make_engine(settings.db_path)
    yield engine
    engine.dispose()


@pytest.fixture
def manager(engine):
    return create_first_manager(engine, "test-manager", "synthetic-password-only")
