import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    port: int = 8765

    @property
    def db_path(self) -> Path:
        return self.data_dir / "store.sqlite3"

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @classmethod
    def from_env(cls) -> "Settings":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
        path = Path(os.environ.get("STORE_DATA_DIR", str(base / "StoreSale"))).expanduser().resolve()
        port = int(os.environ.get("STORE_PORT", "8765"))
        if not 1024 <= port <= 65535:
            raise ValueError("STORE_PORT must be between 1024 and 65535")
        return cls(path, port)

    def prepare(self):
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.data_dir / "backups").mkdir(exist_ok=True, mode=0o700)
