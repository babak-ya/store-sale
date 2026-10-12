# Status — 2026-10-12

**Runnable phase-zero foundation; incomplete prototype. No real store data.**

## Implemented and verified on Linux / Python 3.12

- FastAPI/Jinja Persian RTL setup/login/catalog/opening-stock/backup pages; local CSS.
- Manager creates their own credentials; Argon2id, hashed sessions, expiry, logout and
  inactive-user denial. CSRF, strict Origin/Host, local CSP, escaping, server-side roles.
- File-backed SQLite, SQLAlchemy, Alembic 0002; foreign keys, WAL, FULL sync, busy timeout.
- Explicit BEGIN IMMEDIATE, all-or-nothing posting, payload-checked idempotency,
  immutable ledger triggers, protected product unit after movement.
- Exact money/quantity/step/overflow checks, weighted-average cost snapshots, cumulative
  return rounding helpers. Initial stock form; internal sale valuation service only.
- SQLite Backup API snapshots with schema/integrity/FK validation and SHA-256 manifest.
- Single-process launcher; second invocation checks and uses the running app.
- Baseline at `123a923` (installation guides), matching remote `main` on 2026-10-12:
  **41 tests passed, 1 warning in 11.99s**, freshly installed on Linux/Python 3.12.14.
  Existing test coverage: numerical examples, two connections competing for final stock,
  duplicate commands, stale prices, transaction failure, database lock, abrupt process
  exits before/after commit, auth/role/CSRF/escaping, backup during posting, corrupt and
  unsupported snapshots, restoration to a separate copy, real HTTP launcher checks.
- Browser form-origin correction: use `Referrer-Policy: same-origin`, so local HTML
  POSTs keep their Origin header. Explicit null/external/wrong-port origins still fail.
  Prior work recorded a headless Chromium 154 Linux reproduction and setup check.
  This task reran HTTP/security tests; it did not repeat that browser session.
- `pip check` passed. Install and migrate steps run in `/workspace/store-sale`.

## Whole-gram change prepared for review

- Integer grams, minimum 1 g; exact g/kg conversion and explicit quantity and price
  unit selectors. Inventory display can use g or kg. Counts stay separate integers.
- Schema 0002 converts all legacy weighted quantities, steps, price bases and JSON
  snapshots exactly; fractional history blocks the entire upgrade with diagnostics.
- Verified pre-upgrade snapshots, transactional conversion/guard restoration,
  unchanged integer-rial values and original hashes, compatible legacy retries.
- Runtime rejects old schema rather than displaying milligrams as grams. Hardware
  weight contract now names grams and forbids implicit fractional-gram rounding.
- Final checks on Linux/Python 3.12.14: `.venv/bin/pytest -q` → **57 passed,
  1 warning in 15.38s**; `.venv/bin/python -m pip check` → **No broken requirements
  found**; `git diff --check` → clean. The warning is the existing Starlette/httpx
  TestClient deprecation. Tests use temporary synthetic databases only.
- New coverage: exact migration, 10 incompatible history cases, legacy retries,
  guard preservation, injected late rollback, backup-failure rollback, old-schema
  rejection, exact kg boundaries, manual unit selection/display and unit mismatch.
- See [migration/recovery guidance](docs/GRAM_MIGRATION.md). No production data
  touched. This change is submitted for review; no merge or deployment performed.

Manual product/opening-stock entry needs no scanner, scale or payment terminal.
**A complete manual sale cannot yet be issued:** checkout, payment recording and
printable sale receipts are not implemented. The internal valuation service alone
is not a completed checkout. When built, manual checkout need not require hardware.

## Still required

- Finish phase zero: persisted settings, rotated sanitized logs, fuller auditing,
  normalized operational error/retry UI, startup recovery diagnostics.
- Phase one: complete products/barcodes/prices UI, parties, purchase posting, all money
  ledgers, cash/manual-card checkout with manual weights, receipts and sales/profit reports.
- Phase two: AR/AP allocations, credit, both return workflows, expenses/owner accounts,
  transfers, adjustments, expiry review, day closing, user administration, backup
  records/retention/external destinations and production restore.
- Full acceptance/invariant suite across those ledgers; actual disk-full behavior,
  printer failures, closed-day checks, unknown payment UI and operational recovery
  after OS/power failure during an upgrade. Exception rollback is tested.
- Licensed bundled Persian font, Jalali formatting throughout, cashier documentation,
  Windows onedir package/build script and clean offline Windows machine test.
- Hardware interfaces have no device integration; unavailable terminal never confirms
  payment. No card data is recorded.

## Known limitations

Runtime and ordinary backups require schema 0002. Schema 0001 has the exact
upgrade path described above; legacy archive verification requires an explicit
expected schema. Other snapshot versions remain unsupported. No operational restore endpoint is present. Copy-restoration tests do not
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
and production restoration in a fresh cloud task are **not** claimed.
