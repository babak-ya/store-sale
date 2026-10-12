import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, update, select
from app.web.application import create_app
from app.db import models as m
from app.db.engine import write_transaction
from app.services.auth import hasher


def csrf(client, path):
    page = client.get(path)
    return re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)


def post(client, path, token, **data):
    return client.post(path, data=dict(csrf=token, **data), headers={"Origin": "http://127.0.0.1:8765"})


def test_first_run_catalog_opening_backup_logout(settings):
    app = create_app(settings)
    with TestClient(app, base_url=settings.origin) as client:
        assert client.get("/health").json()["status"] == "ok"
        token = csrf(client, "/setup")
        assert post(client, "/setup", token, username="manager", password="synthetic-password-only").status_code == 200
        token = csrf(client, "/login")
        assert post(client, "/login", token, username="manager", password="synthetic-password-only").status_code == 200
        token = csrf(client, "/")
        assert post(client, "/products", token, sku="001", name="<script>test</script>", kind="weight", step="1", price="۱۵۰۰۰", basis="1", basis_unit="g").status_code == 200
        page = client.get("/")
        assert "&lt;script&gt;" in page.text
        key = re.search(r'name="key" value="([^"]+)"', page.text).group(1)
        assert post(client, "/opening", token, key=key, product_id="1", qty="8", qty_unit="g", value="۸۰۰۰۰", reason="synthetic").status_code == 200
        assert post(client, "/opening", token, key=key, product_id="1", qty="8", qty_unit="g", value="۸۰۰۰۰", reason="synthetic").status_code == 200
        assert post(client, "/backup", token).status_code == 200
        with app.state.engine.connect() as c:
            assert c.execute(select(m.balances.c.value_rial)).scalar() == 800000
        assert post(client, "/logout", token).status_code == 200
        assert client.get("/", follow_redirects=False).status_code == 303


def test_csrf_origin_host_and_setup_cannot_repeat(settings, manager):
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        token = csrf(client, "/login")
        assert client.post("/login", data={"csrf": token}).status_code == 403
        assert client.post("/login", data={"csrf": "bad"}, headers={"Origin": settings.origin}).status_code == 403
        assert client.get("/", headers={"Host": "evil.test"}).status_code == 400
        assert post(client, "/setup", token, username="hacker", password="synthetic-password-only").status_code == 400
        assert client.get("/sale").status_code == 404


def test_cashier_denied_and_disabled_session(settings, engine):
    with write_transaction(engine) as c:
        c.execute(insert(m.users).values(username="cashier", password_hash=hasher.hash("synthetic-password-only"), role="cashier"))
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        token = csrf(client, "/login")
        post(client, "/login", token, username="cashier", password="synthetic-password-only")
        token = csrf(client, "/")
        assert post(client, "/backup", token).status_code == 403
        assert post(client, "/products", token).status_code == 403
        with write_transaction(engine) as c:
            c.execute(update(m.users).values(active=0))
        assert post(client, "/backup", token).status_code == 401


def test_local_forms_preserve_browser_origin(settings):
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        response = client.get("/setup")
        assert response.headers["Referrer-Policy"] == "same-origin"
        assert response.headers["Content-Security-Policy"].find("form-action 'self'") >= 0


@pytest.mark.parametrize("origin", ["null", "https://evil.test", "http://127.0.0.1:9999"])
def test_untrusted_origins_still_rejected(settings, origin):
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        token = csrf(client, "/setup")
        response = client.post("/setup", data=dict(csrf=token, username="manager", password="synthetic-password-only"),
                               headers={"Origin": origin})
        assert response.status_code == 403
        with client.app.state.engine.connect() as c:
            assert c.execute(select(m.users.c.id)).first() is None


def test_manual_kg_quantities_price_units_and_display(settings, manager):
    app = create_app(settings)
    with TestClient(app, base_url=settings.origin) as client:
        token = csrf(client, '/login')
        post(client, '/login', token, username='test-manager', password='synthetic-password-only')
        token = csrf(client, '/')
        assert post(client, '/products', token, sku='kg', name='manual spice', kind='weight', step='1', price='۱۲۰۰۰۰', basis='1', basis_unit='kg').status_code == 200
        assert post(client, '/products', token, sku='count', name='counted', kind='count', step='1', price='10', basis='1', basis_unit='count').status_code == 200
        for basis, unit, kind in [('0.0005','kg','weight'), ('1','kg','count'), ('1','count','weight'), ('1','','weight')]:
            assert post(client, '/products', token, sku='invalid', name='invalid', kind=kind, step='1', price='10', basis=basis, basis_unit=unit).status_code == 400
        for qty, unit, pid in [('0','g','1'), ('0.125','g','1'), ('0.2501','kg','1'), ('1','count','1'), ('1','kg','2'), ('0.5','count','2'), ('1','','1')]:
            assert post(client, '/opening', token, product_id=pid, qty=qty, qty_unit=unit, key='manual-invalid-command', value='10', reason='synthetic').status_code == 400
        assert post(client, '/opening', token, product_id='1', qty='۰٫۲۵۰', qty_unit='kg', key='manual-valid-kg-command', value='100', reason='synthetic').status_code == 200
        # Equivalent g retry is the same command and must not post again.
        assert post(client, '/opening', token, product_id='1', qty='250', qty_unit='g', key='manual-valid-kg-command', value='100', reason='synthetic').status_code == 200
        assert post(client, '/opening', token, product_id='2', qty='1', qty_unit='count', key='manual-valid-count-command', value='10', reason='synthetic').status_code == 200
        assert '250 گرم (g)' in client.get('/').text
        kg_page = client.get('/?weight_unit=kg').text
        assert '0.250 کیلوگرم (kg)' in kg_page and '1 عدد' in kg_page
        assert 'میلی‌گرم' not in kg_page
        assert client.get('/?weight_unit=mg').status_code == 400
        with app.state.engine.connect() as c:
            assert c.execute(select(m.prices.c.basis_qty).where(m.prices.c.product_id == 1)).scalar_one() == 1000
            assert c.execute(select(m.balances.c.qty_base).where(m.balances.c.product_id == 1)).scalar_one() == 250
            assert len(c.execute(select(m.movements)).all()) == 2
