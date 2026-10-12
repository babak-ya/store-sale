import json
import re
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, insert, update
from app.db import models as m
from app.db.engine import write_transaction
from app.services import commerce as s
from app.services.auth import hasher
from app.web.application import create_app
from test_web import csrf, post
from test_commerce import goods, ledger, item


def login(client, username='test-manager'):
    token=csrf(client,'/login')
    assert post(client,'/login',token,username=username,password='synthetic-password-only').status_code==200
    return csrf(client,'/')


@pytest.mark.parametrize('method,confirmation',[('cash',''),('manual_card','yes')])
def test_full_cashier_flow_and_reprints(settings,engine,manager,goods,method,confirmation):
    with TestClient(create_app(settings),base_url=settings.origin) as client:
        token=login(client)
        response=post(client,'/carts',token,kind='sale')
        assert response.status_code==200
        path=response.url.path
        assert post(client,path+'/edit',token,version='0',action='set',product_id=str(goods),qty='0.250',unit='kg').status_code==200
        assert post(client,path+'/edit',token,version='0',action='set',product_id=str(goods),qty='0.250',unit='kg').status_code==409
        assert '250 گرم' in client.get(path).text
        assert 'ادویه' in client.get(path+'?q=spice').text
        data=dict(version='1',method=method,confirmed=confirmation,tendered='4000' if method=='cash' else '')
        if method=='manual_card':
            assert post(client,path+'/post',token,**(data|dict(confirmed=''))).status_code==400
        response=post(client,path+'/post',token,**data)
        assert response.status_code==200
        receipt=response.url.path
        assert 'S-00000001' in response.text and '37,500' not in response.text
        assert '3,750' in response.text and '37500 ریال' in response.text
        before=ledger(engine)
        assert post(client,path+'/post',token,**data).url.path==receipt
        assert client.get(path).url.path==receipt
        for _ in range(3): assert client.get(receipt).status_code==200
        assert ledger(engine)==before
        assert 'S-00000001' in client.get('/sales?q=spice').text
        assert 'S-00000001' in client.get('/sales?q=S-00000001').text
        assert 'S-00000001' not in client.get('/sales?q=missing').text


def test_purchase_supplier_payment_retry_and_escape(settings,engine,manager,goods):
    with TestClient(create_app(settings),base_url=settings.origin) as client:
        token=login(client)
        assert post(client,'/suppliers',token,name='<script>Supplier</script>',phone='000').status_code==200
        response=post(client,'/carts',token,kind='purchase'); path=response.url.path
        response=post(client,path+'/edit',token,version='0',action='set',product_id=str(goods),qty='2',unit='kg',unit_cost='20000',basis='1',basis_unit='kg')
        assert response.status_code==200
        args=dict(version='1',supplier_id='1',paid='10000',method='external_transfer',confirmed='yes')
        response=post(client,path+'/post',token,**args)
        assert response.status_code==200 and 'P-00000001' in response.text
        receipt=response.url.path
        assert '&lt;script&gt;Supplier&lt;/script&gt;' in response.text
        assert post(client,path+'/post',token,**args).url.path==receipt
        key=re.search(r'name="key" value="([^"]+)"',response.text).group(1)
        doc=receipt.split('/')[-1]
        args=dict(key=key,amount='30000',method='external_transfer',confirmed='yes')
        assert post(client,f'/purchases/{doc}/payments',token,**args).status_code==200
        before=ledger(engine)
        assert post(client,f'/purchases/{doc}/payments',token,**args).status_code==200
        assert ledger(engine)==before
        assert 'SP-00000001' in client.get(receipt).text
        with engine.connect() as c: assert s.outstanding(c,doc)==0


def test_stale_stock_refresh_insufficient_stock_and_cart_ownership(settings,engine,manager,goods):
    with TestClient(create_app(settings),base_url=settings.origin) as client:
        token=login(client)
        path=post(client,'/carts',token,kind='sale').url.path
        assert post(client,path+'/edit',token,version='0',action='set',product_id=str(goods),qty='8',unit='kg').status_code==200
        s.post_sale(engine,key=uuid4().hex,actor_id=manager,items=[item(engine,goods,1000)],method='cash')
        assert post(client,path+'/post',token,version='1',method='cash').status_code==409
        assert post(client,path+'/edit',token,version='1',action='refresh').status_code==200
        assert post(client,path+'/post',token,version='2',method='cash').status_code==400
        assert post(client,path+'/edit',token,version='2',action='set',product_id=str(goods),qty='7',unit='kg').status_code==200
        assert post(client,path+'/post',token,version='3',method='cash').status_code==200
        with write_transaction(engine) as c:
            c.execute(insert(m.users).values(username='cashier',password_hash=hasher.hash('synthetic-password-only'),role='cashier'))
        post(client,'/logout',token)
        token=login(client,'cashier')
        assert client.get('/suppliers').status_code==403
        assert client.get(path).status_code==400
        assert post(client,'/carts',token,kind='purchase').status_code==403
        assert post(client,'/suppliers',token,name='Forbidden').status_code==403
        assert post(client,'/carts',token,kind='sale').status_code==200
        assert client.post('/carts',data=dict(csrf=token,kind='sale')).status_code==403


def test_receipt_snapshot_and_real_price_staleness(settings,engine,manager,goods):
    cid=s.new_cart(engine,manager,'sale')
    s.edit_cart(engine,cid,manager,0,'set',dict(product_id=goods,qty=1000))
    with engine.connect() as c: items=json.loads(s.get_cart(c,cid,manager)['items_json'])
    with write_transaction(engine) as c:
        c.execute(insert(m.prices).values(product_id=goods,unit_price_rial=180000,basis_qty=1000,version=2,changed_at='synthetic',changed_by=manager))
    with TestClient(create_app(settings),base_url=settings.origin) as client:
        token=login(client)
        path='/carts/'+cid
        assert post(client,path+'/post',token,version='1',method='cash').status_code==409
        assert post(client,path+'/edit',token,version='1',action='refresh').status_code==200
        assert '18,000' in client.get(path).text
        response=post(client,path+'/post',token,version='2',method='cash')
        receipt=response.url.path
        with write_transaction(engine) as c: c.execute(update(m.products).where(m.products.c.id==goods).values(name='Renamed'))
        response=client.get(receipt)
        assert 'ادویه' in response.text and 'Renamed' not in response.text and '18,000' in response.text
