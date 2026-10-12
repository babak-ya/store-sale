# Local review handoff — milestones 1 and 2

Repository: `C:\Users\babag\codebase\store-sale` on Babak_laptop.
Branch: `feat/cashier-purchases-local`.
Base/HEAD: `9303b45c10011b4cb280ecddb2df2f8cdf276603` (verified gram/kg dependency).
The milestone changes are uncommitted and unpushed for review. Nothing was merged,
published or deployed. No production database or live process was modified.

The pre-existing local change set `Referrer-Policy` to `same-origin`. That exact
behavior is already in the verified dependency. The original local patch is also
preserved in the named stash:
`On main: Preserved pre-milestone same-origin change (already included in gram dependency)`.
There were no integration conflicts and no reset/clean/discard operations.

## Delivered

Atomic cash/manual-card cashier checkout; saved carts; explicit count/g/kg entry
and price bases; stale-state validation; immutable, numbered, printable/reprintable
receipts; searchable/paginated history. Supplier records, purchase carts,
paid/unpaid/part-paid purchases, restocking with weighted-average inventory value,
invoice-specific payments and outstanding supplier balance. Schema 0003 preserves
prior ledgers and adds the minimum records for these workflows.

## Evidence

- Gram/kg baseline: 57 passing tests after correcting Windows SQLite handle closure.
- Final complete suite: **85 passed, 1 existing Starlette/httpx deprecation warning**
  in 24.86 seconds; no broken requirements; whitespace check clean.
- Final real-browser smoke: **passed in headless Microsoft Edge on Windows**.
  It used a newly created temporary database, with no external browser requests.
  Cash replay, fractional-count rejection, g/kg, insufficient stock, manual-card
  confirmation, reprints/print CSS, history, part-paid purchase and settlement passed.
- Final browser ledger: 2 sales, 1 purchase, 1 later supplier payment; zero supplier
  debt; 9500 g valued at 1150000 rial and 2 items valued at 1000 rial; integrity OK.
- Evidence directory:
  `C:\Users\babag\Documents\Codex\2026-10-12\task\browser-evidence-final`
  contains `browser-results.json`, `checkout.png`, `receipt-print.png`,
  `suppliers.png`, and the isolated server log. Screenshots were visually reviewed.
- Full pytest output:
  `C:\Users\babag\Documents\Codex\2026-10-12\task\final-tests.txt`.

## Boundaries

No implementation blocker remains. Physical printing, banking/hardware integration,
production packaging/restore, live-data upgrade and shop readiness are not claimed.
Customer credit, returns and full closing/reporting remain later milestones.
Cash outflows use only recorded cash proceeds; opening cash and owner contributions
are deferred. External transfers only record user-confirmed payments made elsewhere.
See [COMMERCE.md](COMMERCE.md) for behavior, migration and test instructions.

## Exact changed files relative to the verified dependency

- `INSTALL.md`
- `INSTALL_FA.md`
- `README.md`
- `README_FA.md`
- `STATUS.md`
- `app/db/engine.py`
- `app/db/models.py`
- `app/services/backup.py`
- `app/services/commerce.py`
- `app/services/posting.py`
- `app/web/application.py`
- `app/web/commerce.py`
- `app/web/static/style.css`
- `app/web/templates/base.html`
- `app/web/templates/cart.html`
- `app/web/templates/checkout_home.html`
- `app/web/templates/error.html`
- `app/web/templates/home.html`
- `app/web/templates/receipt.html`
- `app/web/templates/sales.html`
- `app/web/templates/suppliers.html`
- `docs/COMMERCE.md`
- `docs/GRAM_MIGRATION.md`
- `docs/MILESTONES_REVIEW.md`
- `migrations/env.py`
- `migrations/schema_0003.py`
- `migrations/versions/0003_commerce.py`
- `scripts/browser_smoke.cjs`
- `tests/test_backup.py`
- `tests/test_commerce.py`
- `tests/test_commerce_migration.py`
- `tests/test_commerce_web.py`
- `tests/test_gram_migration.py`
