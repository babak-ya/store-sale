# StoreSale

Offline Persian grocery/spice store software. **Phase-zero prototype: synthetic data only.**
First-time users: follow [the installation guide](INSTALL.md) or
[راهنمای نصب فارسی](INSTALL_FA.md).
Reviewed specification: [Bobzie's plan](docs/PLAN_FA.txt). See [review](docs/PLAN_REVIEW.md),
[status](STATUS.md), and [Persian operating instructions](README_FA.md).

Target deployment assumes **Windows, one computer, one store, one inventory**.
Development is currently validated on Linux with Python 3.12. Windows packaging and
physical hardware have not been validated.

## Development

```sh
cd /workspace/store-sale
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
export STORE_DATA_DIR=/workspace/store-sale/.local/data
.venv/bin/alembic upgrade head
.venv/bin/pytest -q
.venv/bin/python -m app --no-browser
```

The launcher binds only to `127.0.0.1:8765`, opens a browser by default, and opens the
existing app on a second launch. Use `--no-browser` in cloud development. No services,
Node, Docker, CDN, or network access are needed at runtime. Stop with Ctrl+C.
Create your own manager account on first run; there is no default password or seeded
account. All test accounts and products exist only in pytest's temporary databases.

`STORE_DATA_DIR` selects the data folder; `STORE_PORT` selects a port (1024–65535).
Without an override the data folder is `%LOCALAPPDATA%/StoreSale` on Windows and
`~/.local/share/StoreSale` on Linux. Keep it on a local, non-synchronized disk.
Cloud data resides in ignored `.local/data`; virtualenv, database and generated
backups are not source files.

Money is stored in integer rial and shown as toman; quantities are integer whole grams
or counts (minimum positive quantity: 1 gram or 1 item). Weight input and inventory display offer explicit g/kg selection; 0.250 kg stores
as 250 g. Product price bases have their own unit selector (1 kg or 1 g), and sales
steps remain whole grams. Counted products use items only. Manual entry needs no
connected hardware. The sales
valuation service is internal and tested; **there is no checkout route** until money
and party ledgers can be posted atomically with inventory.

The current schema is `0002` (whole grams); `0001` stored milligrams. Never relabel
old values. The upgrade creates and verifies a legacy snapshot and converts all
weight quantities, price bases and historical snapshots only when exactly divisible
by 1,000. Any fractional-gram value blocks the entire upgrade without rounding or
changing financial data. See [migration and recovery guidance](docs/GRAM_MIGRATION.md)
before upgrading existing data. Do not edit applied migrations or downgrade.

## Backup

The manager's backup button uses SQLite Backup API and validates integrity and foreign
keys, then writes a SHA-256 manifest next to the snapshot in `backups/`. Verify a file:

```sh
.venv/bin/python -c 'from app.services.backup import verify_backup; print(verify_backup("/absolute/path/to/snapshot.sqlite3"))'
```

A copy-restoration test is automated; production restore, session invalidation during
restore, retention schedules, and external-disk workflows are not yet implemented.
Do not replace the live database or copy its standalone file while WAL is active.

Exact runtime and test package versions are pinned in `requirements.lock` and the
direct runtime dependencies in `pyproject.toml`. Versions were resolved through PyPI,
installed with TLS verification, and checked together with `pip check` and tests.
[Dependency license metadata](docs/DEPENDENCY_LICENSES.json) records installed packages;
distribution/license review remains a Windows-packaging prerequisite. The UI uses
system font fallbacks; a licensed bundled Persian font is still pending.
