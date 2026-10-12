# Review of Bobzie's plan

The attached document is the proposed specification, not evidence of a delivered
application. The user's request authorizes review and the start of implementation;
the document's implementation guidance is applied within that scope.

## Assessment

The stack fits the single-computer offline workflow. The strongest decisions are
integer rial/milligram storage, cumulative return rounding, historical cost snapshots,
atomic posting with idempotency, and the explicit distinction between manual card
confirmation and real banking integration. Keeping money, stock and party ledgers
separate avoids counting debt collections as income. The opening acceptance scenario
is numerically consistent; automated tests currently exercise its stock/COGS/profit
portion, not its unimplemented AR/AP/cash ledgers.

Keep the phased delivery and the requirement that phases zero through two plus
Windows/pilot validation are needed for shop use. The 120–200 person-hour estimate
is a planning range, not a promise. Hardware uncertainty does not block the core.

## Decisions made for this first slice

- Python 3.12; exact dependency versions recorded in the lockfile.
- Port 8765, loopback-only, one process; data outside the executable folder.
- No default credentials. User creates the first manager; Argon2id hashes and
  expiring hashed sessions are stored server-side.
- Posting begins with one-line opening stock and internal sale valuation commands.
  Sale UI is withheld until payment/party effects can be included in the same commit.
- Opening inventory is permitted once per product before its first movement.
- Unit kind and quantity step are immutable after movement in this prototype. The
  plan only explicitly forbids changing kind; step-change policy should be revisited
  with hardware precision/version rules before real use.
- No terminal success simulation. The unavailable adapter reports unknown/unavailable.
- No external font or HTMX is used yet; forms are server-rendered and work offline.

## Clarifications to resolve as those features are built

1. Define reservation/allocation ordering for multiple partial payments, and the
   exact unique event keys for AR/AP/refund effects. These must be transaction-tested.
2. Anonymous immediate refunds need an atomic payment+return design; later refunds
   require a named party as the plan states. Do not silently create a generic debtor.
3. Specify cash opening balance and owner contribution documents separately from
   stock opening, including sufficient-cash checks for every outgoing payment.
4. Define the UI for lost responses and unknown card attempts; reusing a command key
   must not depend on the browser inventing a new invoice.
5. Build restore as a controlled stop/validate/safety-copy/swap/restart workflow, not
   a file-upload endpoint that overwrites an open WAL database.
6. Choose Windows build/signing/distribution policy and redistribution licenses before
   packaging. A licensed local Persian font and the chosen hardware need real tests.

No hardware purchase or answers to these future-feature questions are needed to run
the current foundation. OS, scale precision, printer model, payment SDK, scanner and
external backup destination remain prerequisites for deployment approval later.

## Next implementation slice

Extend the schema with parties, money accounts, payments and allocations; add purchase
posting and a cash/manual-card sale flow atomically with stock and ledgers. Then add
barcode search, receipts and reports. Build credit, returns, expenses and day close
with the complete numerical acceptance scenario before calling the product usable.
