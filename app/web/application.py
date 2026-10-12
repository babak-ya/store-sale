import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.config import Settings
from app.db.engine import make_engine, require_current_schema
from app.db import models as m
from app.domain.clock import now_utc, jalali_date
from app.domain.units import DomainError, integer, decimal_text, toman_to_rial, rial_to_toman, quantity, display_weight
from app.services import auth
from app.services.catalog import create_product
from app.services.posting import post_stock, Conflict
from app.services.backup import create_backup

ROOT = Path(__file__).parent


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    settings.prepare()
    engine = make_engine(settings.db_path)
    try:
        with engine.connect() as c:
            require_current_schema(c)
    except BaseException:
        engine.dispose()
        raise

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.engine = engine
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "templates")
    templates.env.filters["toman"] = rial_to_toman
    templates.env.filters["weight"] = display_weight
    failed_logins = deque()

    def user(request, *, manager=False):
        found = auth.current_user(engine, request.cookies.get("session"))
        if not found:
            raise HTTPException(401, "ابتدا وارد شوید")
        if manager and found["role"] != "manager":
            raise HTTPException(403, "دسترسی مدیر لازم است")
        return found

    async def form(request):
        data = await request.form(max_fields=20, max_files=0)
        token = request.cookies.get("csrf", "")
        supplied = data.get("csrf", "")
        if not isinstance(supplied, str) or len(token) < 32 or not secrets.compare_digest(token, supplied):
            raise HTTPException(403, "فرم منقضی یا نامعتبر است؛ صفحه را تازه کنید")
        return data

    def page(request, name, **context):
        csrf = request.cookies.get("csrf") or secrets.token_urlsafe(32)
        status_code = context.pop("code", 200)
        response = templates.TemplateResponse(request=request, name=name,
            context=dict(csrf=csrf, today=jalali_date(now_utc()), **context), status_code=status_code)
        response.set_cookie("csrf", csrf, httponly=True, samesite="strict", max_age=8 * 3600)
        return response

    def number(text):
        value = decimal_text(text)
        if value != value.to_integral_value():
            raise DomainError("عدد صحیح لازم است")
        return integer(int(value), minimum=1)

    @app.middleware("http")
    async def security(request, call_next):
        if request.headers.get("host") != f"127.0.0.1:{settings.port}":
            return HTMLResponse("Host نامعتبر", status_code=400)
        if request.method not in {"GET", "HEAD"}:
            if request.headers.get("origin") != settings.origin:
                return HTMLResponse("Origin نامعتبر", status_code=403)
            if int(request.headers.get("content-length", "0")) > 16384:
                return HTMLResponse("درخواست بیش از حد بزرگ است", status_code=413)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'; connect-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # no-referrer makes browsers send Origin: null for ordinary HTML POSTs.
        # Preserve the local form origin without sending referrers to other sites.
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return page(request, "error.html", message=str(exc), code=409 if isinstance(exc, Conflict) else 400)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        response = page(request, "error.html", message="اطلاعات تکراری یا ناسازگار است؛ هیچ تغییری ثبت نشد", code=409)
        return response

    @app.exception_handler(OperationalError)
    async def operational_error(request, exc):
        response = page(request, "error.html", message="پایگاه داده در دسترس نیست؛ با همان کلید دوباره تلاش کنید", code=503)
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return page(request, "error.html", message=exc.detail, code=exc.status_code)

    @app.get("/health")
    def health():
        with engine.connect() as c:
            c.exec_driver_sql("SELECT 1 FROM alembic_version")
        return {"application": "store-sale", "version": "0.1.0", "status": "ok"}

    @app.get("/setup")
    def setup_page(request: Request):
        if auth.has_users(engine):
            return RedirectResponse("/login", status_code=303)
        return page(request, "auth.html", setup=True)

    @app.post("/setup")
    async def setup(request: Request):
        data = await form(request)
        auth.create_first_manager(engine, str(data.get("username", "")), str(data.get("password", "")))
        return RedirectResponse("/login", status_code=303)

    @app.get("/login")
    def login_page(request: Request):
        if not auth.has_users(engine):
            return RedirectResponse("/setup", status_code=303)
        return page(request, "auth.html", setup=False)

    @app.post("/login")
    async def login(request: Request):
        data = await form(request)
        clock = time.monotonic()
        while failed_logins and failed_logins[0] < clock - 60:
            failed_logins.popleft()
        if len(failed_logins) >= 5:
            raise HTTPException(429, "تلاش‌های زیاد؛ یک دقیقه صبر کنید")
        token = auth.login(engine, str(data.get("username", "")), str(data.get("password", "")))
        if not token:
            failed_logins.append(clock)
            raise HTTPException(401, "نام کاربری یا گذرواژه نادرست است")
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("session", token, httponly=True, samesite="strict", max_age=8 * 3600)
        response.set_cookie("csrf", secrets.token_urlsafe(32), httponly=True, samesite="strict", max_age=8 * 3600)
        return response

    @app.post("/logout")
    async def logout(request: Request):
        await form(request)
        token = request.cookies.get("session")
        if token:
            auth.logout(engine, token)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("session")
        response.delete_cookie("csrf")
        return response

    @app.get("/")
    def home(request: Request):
        found = auth.current_user(engine, request.cookies.get("session"))
        if not found:
            return RedirectResponse("/login", status_code=303)
        with engine.connect() as c:
            rows = c.execute(select(m.products, m.balances.c.qty_base, m.balances.c.value_rial)
                             .join(m.balances)).mappings().all() if found["role"] == "manager" else []
        weight_unit = request.query_params.get("weight_unit", "g")
        if weight_unit not in {"g", "kg"}:
            raise DomainError("واحد نامعتبر است")
        return page(request, "home.html", user=found, products=rows, weight_unit=weight_unit, data_dir=str(settings.data_dir),
                    command_key=secrets.token_urlsafe(24))

    @app.post("/products")
    async def product(request: Request):
        found = user(request, manager=True)
        data = await form(request)
        kind = str(data.get("kind", ""))
        basis = quantity(str(data.get("basis", "")), kind=kind,
                         unit=str(data.get("basis_unit", "")), step=1)
        create_product(engine, actor_id=found["id"], sku=str(data.get("sku", "")), name=str(data.get("name", "")),
                       kind=kind, step=number(str(data.get("step", ""))),
                       price=toman_to_rial(str(data.get("price", ""))), basis=basis)
        return RedirectResponse("/", status_code=303)

    @app.post("/opening")
    async def opening(request: Request):
        found = user(request, manager=True)
        data = await form(request)
        product_id = number(str(data.get("product_id", "")))
        with engine.connect() as c:
            product = c.execute(select(m.products).where(m.products.c.id == product_id)).mappings().first()
        if not product:
            raise DomainError("کالا یافت نشد")
        qty = quantity(str(data.get("qty", "")), kind=product["kind"],
                       unit=str(data.get("qty_unit", "")), step=product["quantity_step"])
        post_stock(engine, key=str(data.get("key", "")), actor_id=found["id"], kind="opening",
                   product_id=product_id, qty=qty,
                   value=toman_to_rial(str(data.get("value", ""))), reason=str(data.get("reason", "")))
        return RedirectResponse("/", status_code=303)

    @app.post("/backup")
    async def backup(request: Request):
        user(request, manager=True)
        await form(request)
        try:
            snapshot = create_backup(settings.db_path, settings.data_dir / "backups")
        except (OSError, ValueError):
            raise HTTPException(503, "پشتیبان ناموفق بود؛ فضای دیسک و دسترسی پوشه را بررسی کنید") from None
        return page(request, "message.html", message=f"پشتیبان سازگار و بررسی‌شده ایجاد شد: {snapshot.name}")

    # There is deliberately no /sale endpoint before payment/party ledgers exist.
    return app
