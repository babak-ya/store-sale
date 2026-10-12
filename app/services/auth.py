import hashlib
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from sqlalchemy import select, insert, delete
from app.db import models as m
from app.db.engine import write_transaction
from app.domain.clock import now_utc
from app.domain.units import DomainError

hasher = PasswordHasher()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def has_users(engine):
    with engine.connect() as c:
        return c.execute(select(m.users.c.id).limit(1)).first() is not None


def create_first_manager(engine, username, password):
    if not 3 <= len(username.strip()) <= 50 or not 12 <= len(password) <= 128:
        raise DomainError("نام کاربری ۳ تا ۵۰ و گذرواژه ۱۲ تا ۱۲۸ نویسه باشد")
    password_hash = hasher.hash(password)
    with write_transaction(engine) as c:
        if c.execute(select(m.users.c.id).limit(1)).first():
            raise DomainError("راه‌اندازی قبلاً انجام شده است")
        result = c.execute(insert(m.users).values(username=username.strip(), password_hash=password_hash, role="manager"))
        return result.inserted_primary_key[0]


def login(engine, username, password):
    if len(username) > 50 or len(password) > 128:
        return None
    with engine.connect() as c:
        user = c.execute(select(m.users).where(m.users.c.username == username)).mappings().first()
    if not user or not user["active"]:
        return None
    try:
        hasher.verify(user["password_hash"], password)
    except (VerificationError, InvalidHashError):
        return None
    token = secrets.token_urlsafe(32)
    with write_transaction(engine) as c:
        # Recheck activity after password hashing.
        if not c.execute(select(m.users.c.id).where(m.users.c.id == user["id"], m.users.c.active == 1)).first():
            return None
        c.execute(insert(m.sessions).values(token_hash=token_hash(token), user_id=user["id"],
                  expires_at=(now_utc() + timedelta(hours=8)).isoformat()))
    return token


def current_user(engine, token):
    if not token or len(token) > 100:
        return None
    with engine.connect() as c:
        row = c.execute(select(m.users).join(m.sessions, m.users.c.id == m.sessions.c.user_id)
                        .where(m.sessions.c.token_hash == token_hash(token),
                               m.sessions.c.expires_at > now_utc().isoformat(), m.users.c.active == 1)).mappings().first()
        return dict(row) if row else None


def logout(engine, token):
    with write_transaction(engine) as c:
        c.execute(delete(m.sessions).where(m.sessions.c.token_hash == token_hash(token)))
