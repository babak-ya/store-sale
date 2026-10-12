# Checkout and purchasing — local milestones 1 and 2

Implemented on `feat/cashier-purchases-local`, based on verified gram/kg commit
`9303b45c10011b4cb280ecddb2df2f8cdf276603`. Not pushed or deployed. All verification
uses temporary synthetic shop databases. The existing shop database is untouched.

## Workflow

1. Sign in. Open **صندوق** and create a sale. Search by product name or SKU.
2. Enter counts as integers or weights with an explicit g/kg selector. Weight
   must convert exactly to whole grams. Selecting an existing cart product replaces
   its quantity. Each price displays its basis, and the server computes the total.
3. Review and choose cash or manually confirmed external card payment. Blank cash
   tender means exact payment; otherwise the receipt shows tender and change.
   This program never charges a card, contacts a terminal or stores card details.
4. Submit once. If the response is lost, resubmit the same form. A saved cart and
   stable request key return the same document. A changed payload conflicts.
   Stock/price changes require deliberate cart refresh and another review.
5. View the numbered receipt. Print through the browser (Ctrl+P). Search sales by
   number, product name/SKU or Gregorian accounting date and reopen to reprint.
   Reprints read immutable snapshots and create no stock or money movement.
6. Managers can add suppliers and create a purchase cart. Enter purchase cost and
   its quantity basis for each line. Enter zero, partial or full initial payment.
   Review posted purchases and record additional payments against a specific invoice.
   Supplier outstanding totals and per-purchase paid/unpaid amounts are derived
   from immutable entries. Both histories are paginated and searchable.

Manager access is required for suppliers, purchases and supplier payments. Cashiers
can use their own sale carts and view/reprint sale receipts. Draft carts persist
across navigation and app restarts; they never reserve stock or affect accounting.

## Accounting and safety

- Integer rial money; explicit display/input in toman (1 toman = 10 rial). No
  browser arithmetic, float money, online scripts or new runtime dependencies.
- Each line rounds `unit price × quantity / basis` half-up to whole rial. Total,
  stock values and payment inputs have signed 64-bit overflow checks.
- Posting uses `BEGIN IMMEDIATE`: active role, idempotency, product/step, price
  version and stock version validation; immutable document/line snapshots;
  payment, stock movements, balances, audit and cart sealing in one transaction.
- Count quantities and grams remain integers. There is no negative stock. Stock
  valuation uses current quantity/value moving weighted average; final depletion
  issues the exact remaining inventory value.
- Purchase lines increase inventory quantity and value. They are **not operating
  expenses**. Supplier payment entries reduce AP, not profit or inventory value.
- Immediate sale payments are cash or confirmed external card. Card receipts use
  `confirmed_manual`, representing a clearing receipt, not a bank integration.
- Supplier payments are cash or explicitly confirmed external transfer. Recorded
  cash outflow cannot exceed net recorded cash receipts. Opening cash, owner
  contributions and complete money-account reconciliation are later work. External
  transfers acknowledge money moved elsewhere; no bank balance is claimed.
- Settlement is invoice-specific; no cross-invoice allocation, supplier advance,
  customer credit, returns, discount UI or day closing is introduced.
- Historical `post_stock(kind='sale')` valuation fixtures retain compatibility.
  They have no payment, are excluded from paid-sale search, and are labelled as
  unpaid legacy valuation documents if opened directly. New cashier routes use
  only the atomic commerce posting service.
- Posted documents, lines, prices, movements, payments, supplier entries, purchase
  supplier snapshots, audit records and idempotency records are immutable.

## Schema upgrade and backup

The application now requires schema **0003**. Existing 0001/0002 databases receive
a validated Backup API snapshot and SHA-256 manifest before migration writes under
a writer lock. Existing 0001 whole-gram conversion remains exact and can still
reject sub-gram history; see [GRAM_MIGRATION.md](GRAM_MIGRATION.md).

0003 widens the document kind constraint through a transactional table rebuild,
copies existing headers unchanged, restores immutable triggers, and adds the
minimal commerce tables. Foreign-key enforcement is disabled only on the migration
connection before BEGIN for SQLite's referenced-table rebuild. The entire database
is checked for foreign-key violations before commit; enforcement is restored and
the connection disposed. Failures roll back schema, rows and version together.
Migration definitions are frozen; current application metadata is not imported by
version scripts. Existing document IDs, ledger entries and command hashes survive.

SQLite connections used by backup and validation now close explicitly before file
rename. Python's SQLite connection context manager alone does not close handles;
that previously caused WinError 32 on Windows.

Do not rehearse on live shop records. Stop old processes and use a separate folder
containing a copy made through the old application's validated backup. Do not copy
an active standalone SQLite file, stamp versions, downgrade or overwrite live data.
For an isolated rehearsal in PowerShell, point `STORE_DATA_DIR` at that folder:

```powershell
$env:STORE_DATA_DIR = 'C:\path\to\isolated-rehearsal'
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m app --no-browser
```

This implementation session did not run the launcher or migrations on the user's
default data directory. An already-running app is not restarted or replaced.
Production restore, packaging, real printers, hardware, power loss/disk-full testing,
full reporting and closing remain outside these milestones.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pip check
git diff --check
```

The tests cover exact accounting fixtures, multi-connection/repeated checkout,
stale prices/stock, insufficient stock, cash and manual-card confirmation, receipt
reprints, role/CSRF/escaping checks, unpaid/part-paid/fully-paid purchases, supplier
payments and overpayment races, injected rollback/retry, and populated 0001/0002
upgrades with pre-upgrade backups and DDL rollback.

Optional actual browser test: `node scripts/browser_smoke.cjs`. Supply
`PYTHON_EXECUTABLE`, `PLAYWRIGHT_MODULE` (an external installed Playwright package),
`BROWSER_EXECUTABLE` (local Edge/Chromium), and optionally `SMOKE_OUTPUT_DIR`.
It starts only a fresh `store-sale-ui-*` temp database on a free loopback port and
terminates its own test server/browser. It leaves synthetic evidence for inspection.
Playwright is a QA tool and is not a runtime dependency.

## راهنمای کوتاه فارسی

از «صندوق» فروش تازه بسازید، کالا را جستجو کنید و مقدار را وارد کنید. برای کالای
وزنی واحد گرم یا کیلوگرم را صریح انتخاب کنید؛ کسری از یک گرم پذیرفته نمی‌شود.
قیمت همیشه همراه مبنای آن نمایش داده می‌شود و همه مبالغ ورودی به تومان هستند.
روش نقدی یا کارت با تأیید دستی را انتخاب کنید. برنامه هیچ عملیات بانکی انجام نمی‌دهد.
برای چاپ رسید از Ctrl+P و برای چاپ دوباره از «سوابق فروش» استفاده کنید.

مدیر در «خرید و تأمین‌کنندگان» تأمین‌کننده را ثبت می‌کند و خرید تازه می‌سازد.
بهای هر ردیف و مبنای آن را وارد کنید. پرداخت صفر یعنی خرید نسیه؛ پرداخت جزئی
یا کامل نیز ممکن است. از فاکتور خرید می‌توانید پرداخت بعدی را ثبت کنید و مانده
بدهی را ببینید. پرداخت نقدی فقط تا میزان وجه نقد ثبت‌شده ممکن است؛ انتقال خارجی
را تنها پس از انجام واقعی آن تأیید کنید. خرید کالا هزینه عملیاتی محسوب نمی‌شود.

در خطا یا قطع پاسخ، همان فرم قبلی را دوباره ارسال کنید. کلید ثبت ثابت مانع ثبت
دوباره می‌شود. اگر قیمت یا موجودی تغییر کرده، سبد را تازه‌سازی و دوباره بازبینی
کنید. فاکتور ثبت‌شده تغییر نمی‌کند؛ مرجوعی و اصلاحات حسابداری در مراحل بعدی هستند.
