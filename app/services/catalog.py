from sqlalchemy import insert
from app.db import models as m
from app.db.engine import write_transaction
from app.domain.clock import now_utc
from app.domain.units import DomainError, integer, normalized_name
from .posting import require_manager


def create_product(engine, *, actor_id, sku, name, kind, step, price, basis):
    integer(step, minimum=1)
    integer(price)
    integer(basis, minimum=1)
    if kind not in {"weight", "count"}:
        raise DomainError("نوع کالا نامعتبر است")
    if not name.strip() or len(name) > 100 or not sku.strip() or len(sku) > 50:
        raise DomainError("نام و کد کالا لازم است (حداکثر ۱۰۰ و ۵۰ حرف)")
    with write_transaction(engine) as c:
        require_manager(c, actor_id)
        result = c.execute(insert(m.products).values(sku=sku.strip(), name=name.strip(),
                   normalized_name=normalized_name(name), kind=kind, quantity_step=step))
        pid = result.inserted_primary_key[0]
        c.execute(insert(m.balances).values(product_id=pid))
        c.execute(insert(m.prices).values(product_id=pid, unit_price_rial=price, basis_qty=basis,
                  version=1, changed_at=now_utc().isoformat(), changed_by=actor_id))
        c.execute(insert(m.audit).values(actor_id=actor_id, action="create_product", reference=str(pid),
                  reason="تعریف کالا", created_at=now_utc().isoformat()))
        return pid
