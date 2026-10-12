# Whole-gram migration (0001 → 0002)

The 2026-10-12 user decision replaces milligrams with **integer grams**, minimum
positive quantity and step **1 g**. A kilogram is 1000 g; price basis is 1 for a gram
and 1000 for a kilogram. Counts remain integers. Money remains integer rial;
prices, costs, net amounts, discounts and inventory values are never rescaled.
The domain accepts kg input only if it converts to whole grams (0.001 kg = 1 g);
the browser opening-stock and price-basis forms explicitly select g/kg or count.
Inventory display also selects g/kg without changing storage. Product selling steps
remain explicitly whole grams (or items). Milligram input is unsupported.
Hardware adapters must report whole grams without silently rounding a reading.

## Before an upgrade

This is still a synthetic-data prototype. No production data was migrated as part
of this change. Stop every old app process and close old browser forms. First make
a verified backup using the old application; preserve both SQLite snapshot and JSON
manifest separately. Test the upgrade on a **separate copy** of that snapshot.
Never copy a live standalone SQLite file with active WAL, overwrite the live file,
run old and new applications against one database, or use `alembic stamp` here.

Point `STORE_DATA_DIR` at the isolated rehearsal folder containing the copied
`store.sqlite3`. From the project directory run:

```sh
.venv/bin/alembic upgrade head
.venv/bin/pytest -q
```

Windows equivalent migration command (not yet verified on Windows):
`.venv\Scripts\alembic.exe upgrade head`.

Both the launcher and Alembic CLI use the same upgrade path. For an existing schema
0001 database, it takes a writer lock, creates a SQLite Backup API snapshot in
`backups/`, validates integrity/FKs/schema, writes a SHA-256 manifest and verifies
it **before migration writes**. A backup failure aborts the upgrade. Empty new
installations migrate directly through 0001 to 0002. Repeated upgrades are no-ops.

## Exact conversion and rejection

For weight products only, the migration checks **every** quantity step, all price
versions' bases, stock balances, document quantities, movement deltas and before/
after quantities, and historical snapshot steps/bases. All must be integers exactly
divisible by 1000 (with valid sign/minimum). Then it divides them by 1000 in one
transaction and marks weight snapshots as grams. Counts, IDs, dates, monetary
values, audit records and original command hashes remain intact. Immutable guards
are restored within that transaction. A failure rolls back DDL, values and version.

Examples: 8000 mg becomes 8 g; a 1000000 mg price basis becomes 1000 g, with the same
rial price. A 125 mg step, 875 mg stock balance, 125 mg historical sale, or fractional
historical price basis **blocks** the upgrade, even with zero current stock. Invalid
snapshot JSON or inconsistent/missing snapshot units also blocks it. The diagnostic
identifies the table, row and field and points here. No automatic rounding,
aggregation, ledger deletion or price rebasing is performed.

If blocked, retain the original schema 0001 database and backup and continue only
with the old application. Do not change immutable history to force conversion.
Data with sub-gram history needs a separately designed, reviewed archival/cutover
workflow retaining that history, or continued use of the old milligram version.
No such workflow is implemented. Even unused sub-gram product settings are rejected
rather than silently changing the product's selling rules.

Legacy idempotency hashes are preserved with a quantity-version marker. An exact
retry supplied in grams reconstructs its original milligram payload for comparison
and returns the original document without posting again. A changed quantity or old
milligram-sized payload conflicts. New commands hash the new quantity version.
Refresh forms after the upgrade; never invent a new key to bypass a retry conflict.

## Verification and recovery

The new app requires schema 0002 and cannot serve a schema 0001 database as grams.
Normal backups validate against 0002. To verify a preserved legacy backup explicitly:

```sh
.venv/bin/python -c 'from app.services.backup import verify_backup; print(verify_backup("/absolute/path/to/legacy.sqlite3", expected_schema="0001"))'
```

This verifies a legacy archive; it does not authorize opening it with the new app.
A failed migration keeps 0001 intact; examine the diagnostic, backup and source
version. A successful migration cannot be downgraded. Rehearse any restoration to
another folder using the matching old app and verified old snapshot, with all
processes stopped. Operational production stop/swap/restart restore is not delivered.

Linux tests cover exact conversion, untouched counts/money, historical rejection,
legacy retries, post-upgrade depletion, immutable guards, repeat upgrades, and an
injected failure after quantity updates. Windows, abrupt OS/power failure during
migration, real disk-full behavior, and actual scales/printers/payment terminals
remain unverified.

## خلاصه فارسی

واحد پایه وزن گرم صحیح و حداقل مقدار ۱ گرم است. قیمت هر گرم مبنای ۱ و هر کیلو
مبنای ۱۰۰۰ دارد. پیش از ارتقا برنامه قبلی را متوقف و پشتیبان را روی کپی جداگانه
آزمایش کنید. ارتقا فقط وقتی همه مقادیر و سوابق وزنی بر ۱۰۰۰ بخش‌پذیر باشند انجام
می‌شود؛ پول تغییر نمی‌کند. وجود حتی یک مقدار کسری از گرم، کل ارتقا را بدون تغییر
داده متوقف می‌کند. خطا نام جدول، ردیف و ستون را نشان می‌دهد. پایگاه داده، سوابق و
پشتیبان را نگه دارید؛ هیچ مقداری را گرد نکنید و نسخه schema را دستی تغییر ندهید.
برای داده غیرقابل تبدیل از برنامه قبلی استفاده کنید تا مسیر حفظ سوابق و انتقال
جداگانه طراحی و تأیید شود. بازیابی عملیاتی و آزمون Windows هنوز تکمیل نشده‌اند.
