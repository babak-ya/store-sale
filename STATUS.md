# Status — 2026-10-10

**Runnable phase-zero foundation; incomplete prototype. No real store data.**

## Implemented and verified on Linux / Python 3.12

- FastAPI/Jinja Persian RTL setup/login/catalog/opening-stock/backup pages; local CSS.
- Manager creates their own credentials; Argon2id, hashed sessions, expiry, logout and
  inactive-user denial. CSRF, strict Origin/Host, local CSP, escaping, server-side roles.
- File-backed SQLite, SQLAlchemy, Alembic 0001; foreign keys, WAL, FULL sync, busy timeout.
- Explicit BEGIN IMMEDIATE, all-or-nothing posting, payload-checked idempotency,
  immutable ledger triggers, protected product unit after movement.
- Exact money/quantity/step/overflow checks, weighted-average cost snapshots, cumulative
  return rounding helpers. Initial stock form; internal sale valuation service only.
- SQLite Backup API snapshots with schema/integrity/FK validation and SHA-256 manifest.
- Single-process launcher; second invocation checks and uses the running app.
- **41 tests passed**: numerical examples, two connections competing for final stock,
  duplicate commands, stale prices, transaction failure, database lock, abrupt process
  exits before/after commit, auth/role/CSRF/escaping, backup during posting, corrupt and
  unsupported snapshots, restoration to a separate copy, real HTTP launcher checks.
- Browser form-origin correction: use `Referrer-Policy: same-origin`, so local HTML
  POSTs keep their Origin header. Explicit null/external/wrong-port origins still fail.
  Reproduced the original null-origin failure and verified successful account creation
  through the login screen with headless Chromium 154 on Linux using a temporary DB.
- `pip check` passed. Install and migrate steps run in `/workspace/store-sale`.

## Still required

- Finish phase zero: persisted settings, rotated sanitized logs, fuller auditing,
  normalized operational error/retry UI, startup recovery diagnostics.
- Phase one: complete products/barcodes/prices UI, parties, purchase posting, all money
  ledgers, cash/manual-card checkout, manual weights, receipts and sales/profit reports.
- Phase two: AR/AP allocations, credit, both return workflows, expenses/owner accounts,
  transfers, adjustments, expiry review, day closing, user administration, backup
  records/retention/external destinations and production restore.
- Full acceptance/invariant suite across those ledgers; actual disk-full behavior,
  printer failures, closed-day checks, unknown payment UI and failed-upgrade recovery.
- Licensed bundled Persian font, Jalali formatting throughout, cashier documentation,
  Windows onedir package/build script and clean offline Windows machine test.
- Hardware interfaces have no device integration; unavailable terminal never confirms
  payment. No card data is recorded.

## Known limitations

Only schema 0001 is supported; older/newer snapshot restoration is rejected, not
migrated. No operational restore endpoint is present. Copy-restoration tests do not
prove the eventual stop/swap/restart procedure. Current schema contains a deliberate
subset of the plan; future migrations must preserve existing ledgers. Initial stock
entry is not an inventory adjustment feature. There is no sales route, receipt,
payment, debt or profit dashboard yet. Product creation has no command idempotency
record; a duplicate SKU is rejected without a second product.

One dependency warning: Starlette currently deprecates its httpx TestClient transport;
tests still execute successfully. Direct official-documentation URL checks from this
cloud runtime were unavailable; package metadata came from PyPI and compatibility
was validated by installation and the executed tests.

Store readiness, Windows compatibility, physical printing, banking integration,
publication, and restoration in a fresh cloud task are **not** claimed.
