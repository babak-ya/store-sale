import re
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
        assert post(client, "/products", token, sku="001", name="<script>test</script>", kind="weight", step="125", price="۱۲۰۰۰۰", basis="1000").status_code == 200
        page = client.get("/")
        assert "&lt;script&gt;" in page.text
        key = re.search(r'name="key" value="([^"]+)"', page.text).group(1)
        assert post(client, "/opening", token, key=key, product_id="1", qty="1000", value="۸۰۰۰۰", reason="synthetic").status_code == 200
        assert post(client, "/opening", token, key=key, product_id="1", qty="1000", value="۸۰۰۰۰", reason="synthetic").status_code == 200
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
