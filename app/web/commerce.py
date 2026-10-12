"""Server-rendered carts: no Javascript, floating-point money or online assets."""
import json
import secrets
from urllib.parse import urlencode
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select, or_
from app.db import models as m
from app.domain.units import quantity, toman_to_rial, decimal_text, integer, normalized_name, line_net, DomainError
from app.services import commerce as service
from app.services.posting import Conflict


def register(app, engine, user, form, page, number):
    def redirect(path):
        return RedirectResponse(path, status_code=303)

    def version(data):
        n = decimal_text(str(data.get('version', '')))
        if n != n.to_integral_value():
            raise DomainError('نسخه سبد نامعتبر است')
        return integer(int(n))

    @app.get('/checkout')
    def checkout_home(request: Request):
        found = user(request)
        with engine.connect() as c:
            rows = c.execute(select(m.carts).where(m.carts.c.actor_id == found['id'], m.carts.c.posted_id.is_(None))
                             .order_by(m.carts.c.id)).mappings().all()
        return page(request, 'checkout_home.html', user=found, carts=rows)

    @app.post('/carts')
    async def create_cart(request: Request):
        found = user(request)
        data = await form(request)
        kind = str(data.get('kind', 'sale'))
        if kind == 'purchase':
            user(request, manager=True)
        cid = service.new_cart(engine, found['id'], kind)
        return redirect('/carts/'+cid)

    @app.get('/carts/{cid}')
    def cart_page(request: Request, cid: str):
        found = user(request)
        q = request.query_params.get('q', '')[:100]
        with engine.connect() as c:
            cart = service.get_cart(c, cid, found['id'])
            if cart['posted_id']:
                return redirect('/documents/'+cart['posted_id'])
            products = c.execute(select(m.products, m.balances.c.qty_base).join(m.balances)
                      .where(m.products.c.active == 1, or_(m.products.c.normalized_name.contains(normalized_name(q), autoescape=True),
                             m.products.c.sku.contains(q, autoescape=True))).order_by(m.products.c.name).limit(50)).mappings().all()
            products = [dict(p, price=service.latest_price(c, p['id'])) for p in products]
            suppliers = c.execute(select(m.suppliers).order_by(m.suppliers.c.name)).mappings().all() if cart['kind']=='purchase' else []
            cash = service.cash_balance(c)
        items = json.loads(cart['items_json'])
        total = 0
        for item in items:
            item['net'] = line_net(item['unit_price_rial'] if cart['kind']=='sale' else item['unit_cost_rial'], item['qty'], item['basis_qty'])
            total = integer(total+item['net'])
        return page(request, 'cart.html', user=found, cart=cart, items=items, total=total,
                    products=products, suppliers=suppliers, q=q, cash=cash)

    @app.post('/carts/{cid}/edit')
    async def cart_edit(request: Request, cid: str):
        found = user(request)
        data = await form(request)
        action = str(data.get('action', ''))
        item = None
        with engine.connect() as c:
            cart = service.get_cart(c, cid, found['id'])
            if action in {'set', 'remove'}:
                pid = number(str(data.get('product_id', '')))
                item = dict(product_id=pid)
                if action == 'set':
                    product = c.execute(select(m.products).where(m.products.c.id == pid)).mappings().first()
                    if not product:
                        raise DomainError('کالا یافت نشد')
                    item['qty'] = quantity(str(data.get('qty', '')), kind=product['kind'], unit=str(data.get('unit','')), step=product['quantity_step'])
                    if cart['kind']=='purchase':
                        item['unit_cost_rial'] = toman_to_rial(str(data.get('unit_cost', '')))
                        item['basis_qty'] = quantity(str(data.get('basis','')), kind=product['kind'], unit=str(data.get('basis_unit','')), step=1)
        service.edit_cart(engine, cid, found['id'], version(data), action, item)
        return redirect('/carts/'+cid)

    @app.post('/carts/{cid}/post')
    async def cart_post(request: Request, cid: str):
        found = user(request)
        data = await form(request)
        with engine.connect() as c:
            cart = service.get_cart(c, cid, found['id'])
        if version(data) != cart['version']:
            raise Conflict('سبد تغییر کرده است؛ دوباره بازبینی کنید')
        common = dict(key=cid, actor_id=found['id'], items=json.loads(cart['items_json']),
                      method=str(data.get('method', '')), confirmed=data.get('confirmed') == 'yes', cart_id=cid)
        if cart['kind']=='sale':
            raw = str(data.get('tendered','')).strip()
            doc = service.post_sale(engine, **common, tendered=toman_to_rial(raw) if raw else None)
        else:
            user(request, manager=True)
            doc = service.post_purchase(engine, **common, supplier_id=number(str(data.get('supplier_id',''))), paid=toman_to_rial(str(data.get('paid','0'))))
        return redirect('/documents/'+doc)

    @app.get('/sales')
    def sales(request: Request):
        found = user(request)
        q = request.query_params.get('q','')[:100]
        page_no = number(request.query_params.get('page', '1'))
        offset = integer((page_no-1)*100)
        with engine.connect() as c:
            # Only complete paid checkouts are receipts; legacy valuation commands
            # remain historical stock fixtures and are not relabelled as payments.
            ids = select(m.lines.c.document_id).where(m.lines.c.snapshot_json.contains(q, autoescape=True))
            rows = c.execute(select(m.documents, m.payments.c.method).join(m.payments, m.payments.c.document_id == m.documents.c.id)
                    .where(m.documents.c.kind=='sale', or_(m.documents.c.number.contains(q, autoescape=True),
                           m.documents.c.accounting_date.contains(q, autoescape=True), m.documents.c.id.in_(ids)))
                    .order_by(m.documents.c.posted_at.desc(), m.documents.c.id).offset(offset).limit(101)).mappings().all()
        return page(request, 'sales.html', user=found, rows=rows[:100], q=q,
                    next_url='/sales?'+urlencode(dict(q=q,page=page_no+1)) if len(rows)>100 else None,
                    prev_url='/sales?'+urlencode(dict(q=q,page=page_no-1)) if page_no>1 else None)

    @app.get('/documents/{doc_id}')
    def receipt(request: Request, doc_id: str):
        found = user(request)
        with engine.connect() as c:
            doc = c.execute(select(m.documents).where(m.documents.c.id == doc_id)).mappings().first()
            if not doc:
                raise HTTPException(404, 'سند یافت نشد')
            if doc['kind'] != 'sale':
                user(request, manager=True)
            rows = c.execute(select(m.lines).where(m.lines.c.document_id == doc_id).order_by(m.lines.c.line_no)).mappings().all()
            rows = [dict(r, snapshot=json.loads(r['snapshot_json'])) for r in rows]
            payment = c.execute(select(m.payments).where(m.payments.c.document_id == doc_id)).mappings().first()
            purchase = c.execute(select(m.purchases).where(m.purchases.c.document_id == doc_id)).mappings().first()
            due = service.outstanding(c, doc_id) if purchase else None
            settlements = c.execute(select(m.documents.c.id, m.documents.c.number, m.payments.c.amount_rial)
                           .join(m.payments, m.payments.c.document_id==m.documents.c.id)
                           .where(m.payments.c.purchase_id==doc_id).order_by(m.documents.c.posted_at)).mappings().all() if purchase else []
        return page(request, 'receipt.html', user=found, doc=doc, rows=rows, payment=payment,
                    purchase=purchase, due=due, settlements=settlements, key=secrets.token_urlsafe(24))

    @app.get('/suppliers')
    def suppliers(request: Request):
        found = user(request, manager=True)
        q = request.query_params.get('q','')[:100]
        page_no = number(request.query_params.get('page', '1'))
        offset = integer((page_no-1)*100)
        with engine.connect() as c:
            rows = [dict(s, due=sum(c.execute(select(m.payables.c.amount_rial).where(m.payables.c.supplier_id==s['id'])).scalars()))
                    for s in c.execute(select(m.suppliers).order_by(m.suppliers.c.name)).mappings().all()]
            purchases = c.execute(select(m.documents, m.purchases.c.supplier_name).join(m.purchases, m.purchases.c.document_id==m.documents.c.id)
                                 .where(or_(m.documents.c.number.contains(q, autoescape=True), m.purchases.c.supplier_name.contains(q, autoescape=True), m.documents.c.accounting_date.contains(q, autoescape=True)))
                                 .order_by(m.documents.c.posted_at.desc(), m.documents.c.id).offset(offset).limit(101)).mappings().all()
            purchases = [dict(p, due=service.outstanding(c,p['id'])) for p in purchases]
        return page(request, 'suppliers.html', user=found, suppliers=rows, purchases=purchases[:100], q=q,
                    next_url='/suppliers?'+urlencode(dict(q=q,page=page_no+1)) if len(purchases)>100 else None,
                    prev_url='/suppliers?'+urlencode(dict(q=q,page=page_no-1)) if page_no>1 else None)

    @app.post('/suppliers')
    async def supplier_create(request: Request):
        found = user(request, manager=True)
        data = await form(request)
        service.create_supplier(engine, actor_id=found['id'], name=str(data.get('name','')), phone=str(data.get('phone','')))
        return redirect('/suppliers')

    @app.post('/purchases/{doc_id}/payments')
    async def supplier_payment(request: Request, doc_id: str):
        found = user(request, manager=True)
        data = await form(request)
        service.pay_supplier(engine, key=str(data.get('key','')), actor_id=found['id'], purchase_id=doc_id,
                 amount=toman_to_rial(str(data.get('amount',''))), method=str(data.get('method','')), confirmed=data.get('confirmed')=='yes')
        return redirect('/documents/'+doc_id)
