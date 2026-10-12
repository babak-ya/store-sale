# Status — 2026-10-12

**Local milestones 1 and 2 implemented for review; synthetic-data verification only.**

Base: verified gram/kg commit `9303b45c10011b4cb280ecddb2df2f8cdf276603`.
Local branch: `feat/cashier-purchases-local`. No milestone commits pushed, merged,
published or deployed. Existing live shop records and the running shop process
were not used for testing or migration.

## Implemented

- Persian RTL, local FastAPI/Jinja/CSS, authentication, CSRF/Origin/Host protection,
  manager/cashier permissions and disabled-user denial.
- Whole-gram g/kg selection, integer counts and rial money, explicit toman
  conversion and quantity-based prices; no browser-float accounting.
- Persistent user-owned carts, product name/SKU search, add/replace/remove lines,
  deliberate stale-state refresh and atomic checkout with exact cash change or
  manually confirmed external card recording. No hardware or internet required.
- Sequential receipts, immutable product/price/cost snapshots, browser printing,
  reprinting and paginated searchable sale history. Reprints have no ledger effects.
- Suppliers, multi-line purchase carts, cost bases, paid/partial/unpaid purchases,
  invoice-specific supplier payments and outstanding balances.
- Inventory moving weighted-average valuation. Purchases increase inventory;
  supplier payments decrease AP. Neither is an operating expense.
- Atomic posting and payload-checked idempotency for checkout, purchase and supplier
  payments; serialized writers; stale prices/stock rejected; no negative inventory,
  supplier overpayment or spending more than recorded available cash.
- Schema 0003, frozen migration definitions, validated pre-upgrade backups,
  transactional header rebuild and new immutable ledgers. Existing 0001/0002
  history, IDs and command hashes survive supported upgrades.
- Windows backup fix: explicitly close SQLite handles before renaming snapshots.

## Verification

- Final Windows suite: **85 passed, 1 existing warning in 24.86s**.
  `pip check`: no broken requirements. `git diff --check`: clean.

- The gram/kg baseline passed all 57 tests locally after the Windows backup fix.
- New tests cover accounting fixtures, simultaneous/repeated checkout, insufficient
  stock, stale state, cash/manual-card validation, immutable receipts and reprints,
  unpaid/part-paid/fully-paid purchases, supplier payment races, roles, escaping,
  CSRF, injected write rollback/retry, and populated migration rollback/retry.
- Actual headless Microsoft Edge UI smoke passed on Windows using external bundled
  Playwright, with a fresh temporary database: real form entry, mixed weight/count
  cart, fractional-count rejection, cash with replayed POST, insufficient stock,
  manual-card confirmation, history search, print CSS, receipt reopen, part-paid
  purchase and supplier settlement. No external browser requests or page errors.
- Browser ledger evidence: 2 sales, 1 purchase, 1 supplier payment; 1 cash receipt,
  1 manual-card receipt and 2 external supplier payments; supplier balance 0;
  inventory `(9500 g, 1150000 rial)` and `(2 items, 1000 rial)`; SQLite integrity OK.
- Existing Starlette/httpx TestClient deprecation warning remains.

See [operating notes and test commands](docs/COMMERCE.md) for precise behavior.

## Later work and limits

- No bank charging, terminal/scale/scanner integration or card details. External
  payment confirmation is a user assertion. Physical printing remains untested;
  browser print layout has been exercised.
- Minimal invoice-specific AP only. No customer credit, returns, cross-invoice
  allocation, advance payments, expenses, full money-account reconciliation,
  opening cash/owner contribution, day close or profit/reporting suite.
- Cash supplier payments can use recorded cash sale proceeds. Other supplier
  payments must be recorded as confirmed external transfers after they occur.
- Product/price administration, barcode aliases, persistent store settings,
  complete audit/log operations, user-administration UI, expiry management,
  Jalali formatting throughout and bundled font remain future work.
- No production restore, Windows installer/package, clean offline-machine pilot,
  disk-full or abrupt OS/power-failure validation. No production-readiness claim.
- Legacy internal sale valuation commands remain for compatibility and fixtures;
  they are excluded from paid checkout history. Opening inventory remains a
  one-time initial-stock operation, not an inventory-adjustment workflow.

Future migrations must preserve existing ledgers. Normal runtime and backups now
require 0003; archive verification supports an explicit expected schema. Do not
downgrade, stamp versions or test migrations on live records.
