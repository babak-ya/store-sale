"""Phase-zero posting engine. Sales are valuation test commands, not a POS API.

Payment/party ledgers and sale routes must be added before actual sales are enabled.
"""
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select, insert, update
from app.db.engine import write_transaction
from app.db import models as m
from app.domain.clock import now_utc, accounting_date
from app.domain.stock import Stock
from app.domain.units import DomainError, integer, line_net


class Conflict(DomainError):
    pass


def require_manager(c, actor_id):
    user = c.execute(select(m.users).where(m.users.c.id == actor_id)).mappings().first()
    if not user or not user["active"] or user["role"] != "manager":
        raise PermissionError("دسترسی مدیر لازم است")


def post_stock(engine, *, key: str, actor_id: int, kind: str, product_id: int,
               qty: int, reason: str, value: int = 0, price_version: int | None = None,
               discount: int = 0) -> str:
    if kind not in {"opening", "sale"}:
        raise DomainError("نوع فرمان نامعتبر است")
    if not isinstance(key, str) or not 16 <= len(key) <= 128:
        raise DomainError("کلید فرمان نامعتبر است")
    integer(qty, minimum=1)
    integer(value)
    integer(discount)
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise DomainError("علت لازم است")
    payload = dict(actor_id=actor_id, kind=kind, product_id=product_id, qty=qty,
                   reason=reason, value=value, price_version=price_version, discount=discount)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with write_transaction(engine) as c:
        require_manager(c, actor_id)
        previous = c.execute(select(m.idempotency).where(m.idempotency.c.key == key)).mappings().first()
        if previous:
            if previous["payload_hash"] != digest:
                raise Conflict("این کلید قبلاً با اطلاعات متفاوت ثبت شده است")
            return previous["result_id"]
        product = c.execute(select(m.products).where(m.products.c.id == product_id)).mappings().first()
        if not product or not product["active"]:
            raise DomainError("کالا فعال نیست")
        if qty % product["quantity_step"]:
            raise DomainError("مقدار با گام کالا سازگار نیست")
        balance = c.execute(select(m.balances).where(m.balances.c.product_id == product_id)).mappings().one()
        old = Stock(balance["qty_base"], balance["value_rial"])
        price = None
        if kind == "opening":
            if c.execute(select(m.movements.c.sequence).where(m.movements.c.product_id == product_id)).first():
                raise Conflict("موجودی افتتاحیه فقط قبل از گردش کالا مجاز است")
            new, cost, net = old.receive(qty, value), value, 0
            dq, dv = qty, value
        else:
            price = c.execute(select(m.prices).where(m.prices.c.product_id == product_id)
                              .order_by(m.prices.c.version.desc())).mappings().first()
            if not price or price_version != price["version"]:
                raise Conflict("قیمت تغییر کرده است؛ قیمت جدید را بررسی کنید")
            net = line_net(price["unit_price_rial"], qty, price["basis_qty"], discount)
            if not net:
                raise DomainError("فروش رایگان هنوز پیاده‌سازی نشده است")
            new, cost = old.issue(qty)
            dq, dv = -qty, -cost
        at = now_utc()
        doc_id, line_id = str(uuid4()), str(uuid4())
        snapshot = {"name": product["name"], "kind": product["kind"],
                    "quantity_step": product["quantity_step"], "discount_rial": discount}
        if price:
            snapshot.update(unit_price_rial=price["unit_price_rial"], basis_qty=price["basis_qty"],
                            price_version=price["version"])
        c.execute(insert(m.documents).values(id=doc_id, number=doc_id, kind=kind,
                  status="posted", accounting_date=accounting_date(at), created_at=at.isoformat(),
                  posted_at=at.isoformat(), actor_id=actor_id, net_rial=net, reason=reason))
        c.execute(insert(m.lines).values(id=line_id, document_id=doc_id, line_no=1, product_id=product_id,
                  qty_base=qty, net_rial=net, cost_rial=cost, snapshot_json=json.dumps(snapshot, ensure_ascii=False)))
        c.execute(insert(m.movements).values(product_id=product_id, document_line_id=line_id,
                  qty_delta=dq, value_delta=dv, quantity_before=old.qty, value_before=old.value,
                  quantity_after=new.qty, value_after=new.value, created_at=at.isoformat()))
        c.execute(update(m.balances).where(m.balances.c.product_id == product_id)
                  .values(qty_base=new.qty, value_rial=new.value, version=balance["version"] + 1))
        c.execute(insert(m.audit).values(actor_id=actor_id, action=kind, reference=doc_id,
                  reason=reason, created_at=at.isoformat()))
        c.execute(insert(m.idempotency).values(key=key, payload_hash=digest, result_id=doc_id))
    return doc_id
