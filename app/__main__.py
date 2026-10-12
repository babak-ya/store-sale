"""Single-process loopback launcher. A second launch opens the existing instance."""
import argparse
import json
import socket
import urllib.request
import webbrowser
import uvicorn
from app.config import Settings
from app.db.migrate import upgrade
from app.services.backup import create_backup
from app.web.application import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.prepare()
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", settings.port))
    except OSError:
        sock.close()
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(settings.origin + "/health", timeout=5) as response:
                found = json.load(response)
            if found.get("application") != "store-sale" or found.get("status") != "ok":
                raise RuntimeError("Port belongs to a different application")
        except Exception as exc:
            raise SystemExit("Port occupied, but a healthy StoreSale instance was not found") from exc
        if not args.no_browser:
            webbrowser.open(settings.origin)
        print("Existing StoreSale instance is running")
        return
    try:
        sock.listen(128)
        # A schema upgrade must preserve a snapshot of an existing database first.
        if settings.db_path.exists():
            import sqlite3
            with sqlite3.connect(settings.db_path) as c:
                row = c.execute("SELECT version_num FROM alembic_version").fetchone()
            if not row or row[0] != "0001":
                create_backup(settings.db_path, settings.data_dir / "backups")
        upgrade()
        app = create_app(settings)
        config = uvicorn.Config(app, host="127.0.0.1", port=settings.port, workers=1,
                                access_log=False, log_level="warning")
        if not args.no_browser:
            # Server is about to start; browser may need a refresh on a slow machine.
            webbrowser.open(settings.origin)
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        sock.close()


if __name__ == "__main__":
    main()
