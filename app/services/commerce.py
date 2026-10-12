"""Hardware-independent posting; every command uses one SQLite writer transaction.

Cash is the net recorded cash received less cash paid. External supplier transfers
are manual records, not bank instructions or a reconciled bank balance.
"""
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select, insert, update
from app.db import models as m
from app.db.engine import write_transaction
from app.domain.clock import now_utc, accounting_date
from app.domain.stock import Stock
from app.domain.units import DomainError, integer, line_net
from app.services.posting import Conflict


def actor(c, actor_id, manager=False):
    row = c.execute(select(m.users).where(m.users.c.id == actor_id)).mappings().first()
    if not row or not row['active'] or (manager and row['role'] != 'manager'):
        raise PermissionError('دسترسی مجاز نیست')
    return row


def command(c, key, payload):
    if not isinstance(key, str) or not 16 <= len(key) <= 128:
        raise DomainError('کلید ثبت نامعتبر است')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    prior = c.execute(select(m.idempotency).where(m.idempotency.c.key == key)).mappings().first()
    if prior and prior['payload_hash'] != digest:
        raise Conflict('این درخواست قبلاً با اطلاعات دیگری ثبت شده است؛ سوابق را بررسی کنید')
    return digest, prior['result_id'] if prior else None


def finish(c, key, digest, doc, actor_id, kind):
    c.execute(insert(m.idempotency).values(key=key, payload_hash=digest, result_id=doc, quantity_version=2))
    c.execute(insert(m.audit).values(actor_id=actor_id, action=kind, reference=doc,
              reason='ثبت قطعی', created_at=now_utc().isoformat()))


def document(c, kind, total, actor_id, reason):
    integer(total, minimum=1)
    at = now_utc()
    current = c.execute(select(m.counters.c.value).where(m.counters.c.kind == kind)).scalar()
    number = integer((current or 0) + 1, minimum=1)
    if current is None:
        c.execute(insert(m.counters).values(kind=kind, value=number))
    else:
        c.execute(update(m.counters).where(m.counters.c.kind == kind).values(value=number))
    prefix = {'sale': 'S', 'purchase': 'P', 'supplier_payment': 'SP'}[kind]
    doc = uuid4().hex
    c.execute(insert(m.documents).values(id=doc, number=f'{prefix}-{number:08d}', kind=kind,
              status='posted', accounting_date=accounting_date(at), created_at=at.isoformat(),
              posted_at=at.isoformat(), actor_id=actor_id, net_rial=total, reason=reason))
    return doc


def cash_balance(c):
    rows = c.execute(select(m.payments.c.direction, m.payments.c.amount_rial).where(m.payments.c.method == 'cash'))
    return sum(amount if direction == 'in' else -amount for direction, amount in rows)


def payment(c, doc, amount, method, direction, confirmed, tendered=None, purchase_id=None):
    integer(amount, minimum=1)
    allowed = {'cash', 'manual_card'} if direction == 'in' else {'cash', 'external_transfer'}
    if method not in allowed:
        raise DomainError('روش پرداخت نامعتبر است')
    if method != 'cash' and confirmed is not True:
        raise DomainError('پرداخت خارج از برنامه را صریحاً تأیید کنید؛ برنامه پولی منتقل نمی‌کند')
    if direction == 'out' and method == 'cash' and amount > cash_balance(c):
        raise DomainError('وجه نقد ثبت‌شده کافی نیست؛ پرداخت خارجی را فقط پس از انجام واقعی ثبت کنید')
    if direction == 'in' and method == 'cash':
        integer(cash_balance(c) + amount)
    tendered = amount if tendered is None else integer(tendered)
    if tendered < amount or (method != 'cash' and tendered != amount) or (direction == 'out' and tendered != amount):
        raise DomainError('مبلغ دریافتی نامعتبر یا کمتر از جمع فاکتور است')
    c.execute(insert(m.payments).values(id=uuid4().hex, document_id=doc, purchase_id=purchase_id,
              amount_rial=amount, direction=direction, method=method, tendered_rial=tendered,
              change_rial=tendered-amount, status='confirmed_cash' if method == 'cash' else 'confirmed_manual',
              created_at=now_utc().isoformat()))


def latest_price(c, pid):
    return c.execute(select(m.prices).where(m.prices.c.product_id == pid)
                     .order_by(m.prices.c.version.desc())).mappings().first()


def prepare(c, items, kind):
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise DomainError('سبد باید بین یک و صد ردیف داشته باشد')
    prepared, seen, total = [], set(), 0
    for item in items:
        pid, qty = integer(item['product_id'], minimum=1), integer(item['qty'], minimum=1)
        if pid in seen:
            raise DomainError('هر کالا فقط یک ردیف دارد؛ مقدار همان ردیف را تغییر دهید')
        seen.add(pid)
        product = c.execute(select(m.products).where(m.products.c.id == pid)).mappings().first()
        if not product or not product['active'] or qty % product['quantity_step']:
            raise DomainError('کالا یا گام مقدار نامعتبر است')
        bal = c.execute(select(m.balances).where(m.balances.c.product_id == pid)).mappings().one()
        old = Stock(bal['qty_base'], bal['value_rial'])
        snap = dict(name=product['name'], sku=product['sku'], kind=product['kind'],
                    quantity_unit='g' if product['kind']=='weight' else 'count', quantity_step=product['quantity_step'])
        if kind == 'sale':
            price = latest_price(c, pid)
            if not price or integer(item['price_version'], minimum=1) != price['version']:
                raise Conflict('قیمت تغییر کرده است؛ سبد را بازبینی و تازه‌سازی کنید')
            if integer(item['stock_version']) != bal['version']:
                raise Conflict('موجودی تغییر کرده است؛ سبد را بازبینی و تازه‌سازی کنید')
            net = line_net(price['unit_price_rial'], qty, price['basis_qty'])
            new, cost = old.issue(qty)
            snap.update(unit_price_rial=price['unit_price_rial'], basis_qty=price['basis_qty'], price_version=price['version'])
        else:
            unit_cost, basis = integer(item['unit_cost_rial']), integer(item['basis_qty'], minimum=1)
            net = line_net(unit_cost, qty, basis)
            cost, new = net, old.receive(qty, net)
            snap.update(unit_price_rial=unit_cost, basis_qty=basis)
        total = integer(total + net)
        prepared.append((pid, qty, net, cost, old, new, bal['version'], snap))
    integer(total, minimum=1)
    return prepared, total


def stock_lines(c, doc, prepared):
    for no, (pid, qty, net, cost, old, new, version, snap) in enumerate(prepared, 1):
        line = uuid4().hex
        c.execute(insert(m.lines).values(id=line, document_id=doc, line_no=no, product_id=pid,
                  qty_base=qty, net_rial=net, cost_rial=cost, snapshot_json=json.dumps(snap, ensure_ascii=False)))
        c.execute(insert(m.movements).values(product_id=pid, document_line_id=line,
                  qty_delta=new.qty-old.qty, value_delta=new.value-old.value,
                  quantity_before=old.qty, value_before=old.value, quantity_after=new.qty, value_after=new.value,
                  created_at=now_utc().isoformat()))
        c.execute(update(m.balances).where(m.balances.c.product_id == pid)
                  .values(qty_base=new.qty, value_rial=new.value, version=integer(version+1)))


def post_sale(engine, *, key, actor_id, items, method, confirmed=False, tendered=None, cart_id=None):
    payload = dict(action='checkout', actor_id=actor_id, items=items, method=method, confirmed=confirmed, tendered=tendered, cart_id=cart_id)
    with write_transaction(engine) as c:
        actor(c, actor_id)
        digest, previous = command(c, key, payload)
        if previous:
            return previous
        prepared, total = prepare(c, items, 'sale')
        doc = document(c, 'sale', total, actor_id, 'فروش صندوق')
        stock_lines(c, doc, prepared)
        payment(c, doc, total, method, 'in', confirmed, tendered)
        finish(c, key, digest, doc, actor_id, 'sale')
        seal_cart(c, cart_id, actor_id, 'sale', items, doc)
        return doc


def create_supplier(engine, *, actor_id, name, phone=''):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or not isinstance(phone, str) or len(phone) > 50:
        raise DomainError('نام یا تلفن تأمین‌کننده نامعتبر است')
    with write_transaction(engine) as c:
        actor(c, actor_id, True)
        result = c.execute(insert(m.suppliers).values(name=name.strip(), phone=phone.strip(), created_by=actor_id))
        sid = result.inserted_primary_key[0]
        c.execute(insert(m.audit).values(actor_id=actor_id, action='supplier_create', reference=str(sid),
                  reason='ایجاد تأمین‌کننده', created_at=now_utc().isoformat()))
        return sid


def payable(c, supplier_id, purchase_id, doc, amount, event):
    c.execute(insert(m.payables).values(supplier_id=supplier_id, purchase_id=purchase_id,
              document_id=doc, amount_rial=amount, event=event))


def outstanding(c, purchase_id):
    return sum(c.execute(select(m.payables.c.amount_rial).where(m.payables.c.purchase_id == purchase_id)).scalars())


def post_purchase(engine, *, key, actor_id, supplier_id, items, paid=0, method='cash', confirmed=False, cart_id=None):
    integer(paid)
    integer(supplier_id, minimum=1)
    payload = dict(action='purchase', actor_id=actor_id, supplier_id=supplier_id, items=items, paid=paid, method=method, confirmed=confirmed, cart_id=cart_id)
    with write_transaction(engine) as c:
        actor(c, actor_id, True)
        digest, previous = command(c, key, payload)
        if previous:
            return previous
        supplier = c.execute(select(m.suppliers).where(m.suppliers.c.id == supplier_id)).mappings().first()
        if not supplier:
            raise DomainError('تأمین‌کننده یافت نشد')
        prepared, total = prepare(c, items, 'purchase')
        if paid > total:
            raise DomainError('پرداخت از جمع خرید بیشتر است')
        balance = sum(c.execute(select(m.payables.c.amount_rial).where(m.payables.c.supplier_id == supplier_id)).scalars())
        integer(balance + total - paid)
        doc = document(c, 'purchase', total, actor_id, 'خرید موجودی')
        c.execute(insert(m.purchases).values(document_id=doc, supplier_id=supplier_id, supplier_name=supplier['name']))
        stock_lines(c, doc, prepared)
        payable(c, supplier_id, doc, doc, total, 'purchase')
        if paid:
            payment(c, doc, paid, method, 'out', confirmed, purchase_id=doc)
            payable(c, supplier_id, doc, doc, -paid, 'payment')
        finish(c, key, digest, doc, actor_id, 'purchase')
        seal_cart(c, cart_id, actor_id, 'purchase', items, doc)
        return doc


def pay_supplier(engine, *, key, actor_id, purchase_id, amount, method, confirmed=False):
    integer(amount, minimum=1)
    payload = dict(action='supplier_payment', actor_id=actor_id, purchase_id=purchase_id, amount=amount, method=method, confirmed=confirmed)
    with write_transaction(engine) as c:
        actor(c, actor_id, True)
        digest, previous = command(c, key, payload)
        if previous:
            return previous
        purchase = c.execute(select(m.purchases).where(m.purchases.c.document_id == purchase_id)).mappings().first()
        if not purchase or amount > outstanding(c, purchase_id):
            raise Conflict('خرید یافت نشد یا پرداخت از مانده بدهی بیشتر است')
        doc = document(c, 'supplier_payment', amount, actor_id, 'پرداخت بدهی تأمین‌کننده')
        payment(c, doc, amount, method, 'out', confirmed, purchase_id=purchase_id)
        payable(c, purchase['supplier_id'], purchase_id, doc, -amount, 'payment')
        finish(c, key, digest, doc, actor_id, 'supplier_payment')
        return doc


def new_cart(engine, actor_id, kind):
    if kind not in {'sale', 'purchase'}:
        raise DomainError('نوع سبد نامعتبر است')
    with write_transaction(engine) as c:
        actor(c, actor_id, kind == 'purchase')
        cid = uuid4().hex
        c.execute(insert(m.carts).values(id=cid, actor_id=actor_id, kind=kind, version=0, items_json='[]'))
        return cid


def get_cart(c, cid, actor_id):
    row = c.execute(select(m.carts).where(m.carts.c.id == cid, m.carts.c.actor_id == actor_id)).mappings().first()
    if not row:
        raise DomainError('سبد یافت نشد')
    actor(c, actor_id, row['kind'] == 'purchase')
    return dict(row)


def edit_cart(engine, cid, actor_id, version, action, item=None):
    with write_transaction(engine) as c:
        cart = get_cart(c, cid, actor_id)
        if cart['posted_id'] or integer(version) != cart['version']:
            raise Conflict('سبد تغییر کرده یا ثبت شده است؛ دوباره آن را باز کنید')
        items = json.loads(cart['items_json'])
        if action == 'remove':
            items = [i for i in items if i['product_id'] != item['product_id']]
        elif action == 'set':
            pid = integer(item['product_id'], minimum=1)
            product = c.execute(select(m.products).where(m.products.c.id == pid)).mappings().first()
            if not product or not product['active'] or integer(item['qty'], minimum=1) % product['quantity_step']:
                raise DomainError('کالا یا مقدار نامعتبر است')
            entry = dict(item)
            if cart['kind'] == 'sale':
                price = latest_price(c, pid)
                bal = c.execute(select(m.balances).where(m.balances.c.product_id == pid)).mappings().one()
                entry.update(price_version=price['version'], stock_version=bal['version'], unit_price_rial=price['unit_price_rial'], basis_qty=price['basis_qty'])
            else:
                integer(entry['unit_cost_rial'])
                integer(entry['basis_qty'], minimum=1)
            entry.update(name=product['name'], kind=product['kind'])
            items = [i for i in items if i['product_id'] != pid] + [entry]
        elif action == 'refresh' and cart['kind'] == 'sale':
            for entry in items:
                price = latest_price(c, entry['product_id'])
                bal = c.execute(select(m.balances).where(m.balances.c.product_id == entry['product_id'])).mappings().one()
                entry.update(price_version=price['version'], stock_version=bal['version'], unit_price_rial=price['unit_price_rial'], basis_qty=price['basis_qty'])
        else:
            raise DomainError('عملیات نامعتبر است')
        if len(items)>100:
            raise DomainError('حداکثر صد ردیف مجاز است')
        c.execute(update(m.carts).where(m.carts.c.id == cid).values(items_json=json.dumps(items, ensure_ascii=False), version=integer(version+1)))


def seal_cart(c, cid, actor_id, kind, items, doc):
    if cid is None:
        return
    cart = get_cart(c, cid, actor_id)
    if cart['posted_id'] or cart['kind'] != kind or json.loads(cart['items_json']) != items:
        raise Conflict('سبد تغییر کرده است؛ دوباره بازبینی کنید')
    c.execute(update(m.carts).where(m.carts.c.id == cid).values(posted_id=doc))
