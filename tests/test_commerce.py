import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import select, insert, update, event
from sqlalchemy.exc import IntegrityError
from app.db import models as m
from app.db.engine import write_transaction, make_engine
from app.domain.units import DomainError, MAX_INT
from app.services import commerce as s
from app.services.posting import post_stock, Conflict
from app.services.catalog import create_product


@pytest.fixture
def goods(engine, manager):
    pid = create_product(engine, actor_id=manager, sku='spice', name='ادویه', kind='weight', step=1, price=150000, basis=1000)
    post_stock(engine, key=uuid4().hex, actor_id=manager, kind='opening', product_id=pid, qty=8000, value=800000, reason='synthetic')
    return pid


def item(engine, pid, qty):
    with engine.connect() as c:
        version = c.execute(select(m.balances.c.version).where(m.balances.c.product_id==pid)).scalar()
        price = s.latest_price(c, pid)
    return dict(product_id=pid, qty=qty, stock_version=version, price_version=price['version'])


def sale(engine, manager, pid, qty=1000, **kw):
    return s.post_sale(engine, key=kw.pop('key',uuid4().hex), actor_id=manager, items=kw.pop('items',[item(engine,pid,qty)]), method=kw.pop('method','cash'), **kw)


def purchase(engine, manager, pid, supplier_id, **kw):
    return s.post_purchase(engine, key=kw.pop('key',uuid4().hex), actor_id=manager, supplier_id=supplier_id,
           items=kw.pop('items',[dict(product_id=pid,qty=2000,unit_cost_rial=200000,basis_qty=1000)]), **kw)


def ledger(engine):
    with engine.connect() as c:
        result = {}
        for table in (m.documents,m.lines,m.movements,m.payments,m.payables,m.idempotency,m.counters,m.audit,m.balances):
            result[table.name] = [tuple(row) for row in c.execute(select(table))]
        assert c.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
        for b in c.execute(select(m.balances)).mappings():
            entries = c.execute(select(m.movements).where(m.movements.c.product_id==b['product_id'])).mappings().all()
            assert b['qty_base']==sum(e['qty_delta'] for e in entries)
            assert b['value_rial']==sum(e['value_delta'] for e in entries)
        return result


def test_accounting_purchase_weighted_average_and_payments(engine, manager, goods):
    # Opening Q=8000,V=800000; sell 1000 for 150000, COGS=100000.
    sold = sale(engine,manager,goods,tendered=200000)
    supplier = s.create_supplier(engine,actor_id=manager,name='تأمین‌کننده')
    bought = purchase(engine,manager,goods,supplier,paid=100000)
    with engine.connect() as c:
        assert c.execute(select(m.balances.c.qty_base,m.balances.c.value_rial)).one()==(9000,1100000)
        assert s.outstanding(c,bought)==300000
        assert s.cash_balance(c)==50000
        p=c.execute(select(m.payments).where(m.payments.c.document_id==sold)).mappings().one()
        assert (p['amount_rial'],p['tendered_rial'],p['change_rial'])==(150000,200000,50000)
    sold2=sale(engine,manager,goods,qty=3000,method='manual_card',confirmed=True)
    with engine.connect() as c:
        row=c.execute(select(m.lines).where(m.lines.c.document_id==sold2)).mappings().one()
        assert (row['net_rial'],row['cost_rial'])==(450000,366667)
        assert c.execute(select(m.balances.c.qty_base,m.balances.c.value_rial)).one()==(6000,733333)
    key=uuid4().hex
    args=dict(key=key,actor_id=manager,purchase_id=bought,amount=300000,method='external_transfer',confirmed=True)
    pay=s.pay_supplier(engine,**args)
    assert s.pay_supplier(engine,**args)==pay
    with engine.connect() as c:
        assert s.outstanding(c,bought)==0
        assert s.cash_balance(c)==50000
        assert c.execute(select(m.documents.c.kind).where(m.documents.c.id==pay)).scalar()=='supplier_payment'
    sale(engine,manager,goods,qty=6000)
    with engine.connect() as c:
        assert c.execute(select(m.balances.c.qty_base,m.balances.c.value_rial)).one()==(0,0)
    ledger(engine)


@pytest.mark.parametrize('paid',[0,100000,400000])
def test_unpaid_part_paid_fully_paid_repeat_purchase(engine,manager,goods,paid):
    supplier=s.create_supplier(engine,actor_id=manager,name='Supplier')
    key=uuid4().hex
    args=dict(paid=paid,method='external_transfer',confirmed=True,key=key)
    doc=purchase(engine,manager,goods,supplier,**args)
    before=ledger(engine)
    assert purchase(engine,manager,goods,supplier,**args)==doc
    assert ledger(engine)==before
    with engine.connect() as c:
        assert s.outstanding(c,doc)==400000-paid
    with pytest.raises(Conflict):
        purchase(engine,manager,goods,supplier,**(args|dict(paid=1)))


def test_duplicate_checkout_and_competing_last_stock(settings,engine,manager,goods):
    items=[item(engine,goods,8000)]
    key=uuid4().hex
    def run(k):
        other=make_engine(settings.db_path)
        try:
            return s.post_sale(other,key=k,actor_id=manager,items=items,method='cash')
        except DomainError:
            return 'conflict'
        finally:
            other.dispose()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,[key,key]))
    assert results[0]==results[1] and results[0]!='conflict'
    assert run(uuid4().hex)=='conflict'
    with engine.connect() as c:
        assert len(c.execute(select(m.payments)).all())==1
        assert c.execute(select(m.documents.c.number).where(m.documents.c.kind=='sale')).scalar()=='S-00000001'
    ledger(engine)


def test_two_different_keys_compete(engine,manager,goods):
    items=[item(engine,goods,8000)]
    def run(_):
        try:
            return sale(engine,manager,goods,items=items)
        except Conflict:
            return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,range(2)))
    assert results.count('stale')==1
    ledger(engine)


@pytest.mark.parametrize('failure',['stock','price','card','cash','overflow','duplicate'])
def test_validation_rolls_back_every_effect(engine,manager,goods,failure):
    args={}
    if failure=='stock': args['items']=[item(engine,goods,8001)]
    if failure=='price': args['items']=[item(engine,goods,1)|dict(price_version=2)]
    if failure=='card': args['method']='manual_card'
    if failure=='cash': args['tendered']=1
    if failure=='overflow': args['items']=[item(engine,goods,MAX_INT)]
    if failure=='duplicate': args['items']=[item(engine,goods,1),item(engine,goods,1)]
    before=ledger(engine)
    with pytest.raises(DomainError): sale(engine,manager,goods,**args)
    assert ledger(engine)==before


@pytest.mark.parametrize('table',['document_lines','stock_movements','payments','supplier_entries','idempotency_records'])
def test_late_failure_then_retry(engine,manager,goods,table):
    supplier=s.create_supplier(engine,actor_id=manager,name='Supplier')
    args=dict(key=uuid4().hex,paid=1,method='external_transfer',confirmed=True)
    before=ledger(engine)
    def fail(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('INSERT INTO '+table): raise RuntimeError('injected write failure')
    event.listen(engine,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError,match='injected'): purchase(engine,manager,goods,supplier,**args)
    finally:
        event.remove(engine,'before_cursor_execute',fail)
    assert ledger(engine)==before
    purchase(engine,manager,goods,supplier,**args)
    ledger(engine)


def test_supplier_overpay_cash_shortfall_and_concurrent_settlement(engine,manager,goods):
    supplier=s.create_supplier(engine,actor_id=manager,name='Supplier')
    bought=purchase(engine,manager,goods,supplier)
    before=ledger(engine)
    with pytest.raises(DomainError):
        s.pay_supplier(engine,key=uuid4().hex,actor_id=manager,purchase_id=bought,amount=1,method='cash')
    with pytest.raises(Conflict):
        s.pay_supplier(engine,key=uuid4().hex,actor_id=manager,purchase_id=bought,amount=400001,method='external_transfer',confirmed=True)
    assert ledger(engine)==before
    def run(_):
        try: return s.pay_supplier(engine,key=uuid4().hex,actor_id=manager,purchase_id=bought,amount=400000,method='external_transfer',confirmed=True)
        except Conflict: return 'settled'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,range(2)))
    assert results.count('settled')==1
    ledger(engine)


def test_immutability_snapshot_and_roles(engine,manager,goods):
    doc=sale(engine,manager,goods)
    with write_transaction(engine) as c:
        c.execute(update(m.products).where(m.products.c.id==goods).values(name='Renamed'))
        cashier=c.execute(insert(m.users).values(username='cashier',password_hash='unused',role='cashier')).inserted_primary_key[0]
    with engine.connect() as c:
        snap=json.loads(c.execute(select(m.lines.c.snapshot_json).where(m.lines.c.document_id==doc)).scalar())
        assert snap['name']=='ادویه' and snap['basis_qty']==1000
    sale(engine,cashier,goods)
    with pytest.raises(PermissionError): s.create_supplier(engine,actor_id=cashier,name='Denied')
    for table in (m.documents,m.lines,m.payments,m.movements):
        with pytest.raises(IntegrityError):
            with write_transaction(engine) as c: c.execute(table.delete())
    ledger(engine)


def test_cart_repeat_edit_sealing_and_stale_cart(engine,manager,goods):
    cid=s.new_cart(engine,manager,'sale')
    s.edit_cart(engine,cid,manager,0,'set',dict(product_id=goods,qty=1000))
    with pytest.raises(Conflict): s.edit_cart(engine,cid,manager,0,'set',dict(product_id=goods,qty=1000))
    with engine.connect() as c: items=json.loads(s.get_cart(c,cid,manager)['items_json'])
    doc=s.post_sale(engine,key=cid,actor_id=manager,items=items,method='cash',cart_id=cid)
    assert s.post_sale(engine,key=cid,actor_id=manager,items=items,method='cash',cart_id=cid)==doc
    with pytest.raises(Conflict): s.edit_cart(engine,cid,manager,1,'remove',dict(product_id=goods))
    with pytest.raises(Conflict): s.post_sale(engine,key=uuid4().hex,actor_id=manager,items=[item(engine,goods,1000)],method='cash',cart_id=cid)
    with engine.connect() as c: assert s.get_cart(c,cid,manager)['posted_id']==doc
    ledger(engine)
