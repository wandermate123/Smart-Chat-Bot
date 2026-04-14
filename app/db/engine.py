import os
from functools import lru_cache
from urllib.parse import quote

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


def normalize_database_url(url: str) -> str:
    """Supabase/Neon often give postgresql:// which selects psycopg2; we use psycopg v3."""
    if url.startswith("postgresql://") and not url.startswith("postgresql+psycopg"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def build_database_url(
    *,
    host: str,
    user: str,
    password: str,
    database: str = "postgres",
    port: int = 5432,
    sslmode: str | None = "require",
) -> str:
    """Build a psycopg v3 URL with proper encoding (passwords with @ # ] etc.)."""
    u = quote(user, safe="")
    p = quote(password, safe="")
    q = f"?sslmode={quote(sslmode, safe='')}" if sslmode else ""
    return f"postgresql+psycopg://{u}:{p}@{host}:{port}/{database}{q}"


def resolve_database_url_from_env() -> str | None:
    """Read DATABASE_URL or DATABASE_HOST + DATABASE_PASSWORD (+ optional pieces) from os.environ.

    Used by Alembic so migrations run without loading full app Settings (Meta tokens, etc.).
    """
    disabled = (os.environ.get("DATABASE_ENABLED") or "").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ) or (os.environ.get("USE_POSTGRES") or "").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    )
    if disabled:
        return None
    raw = os.environ.get("DATABASE_URL")
    if raw and str(raw).strip():
        return str(raw).strip()
    host = (os.environ.get("DATABASE_HOST") or "").strip()
    password = os.environ.get("DATABASE_PASSWORD")
    if not host or password is None:
        return None
    user = os.environ.get("DATABASE_USER") or "postgres"
    database = os.environ.get("DATABASE_NAME") or "postgres"
    port_s = os.environ.get("DATABASE_PORT") or "5432"
    try:
        port = int(port_s)
    except ValueError:
        port = 5432
    sslmode = os.environ.get("DATABASE_SSLMODE", "require")
    ssl = sslmode if sslmode else None
    return build_database_url(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        sslmode=ssl,
    )


@lru_cache(maxsize=4)
def get_engine(database_url: str):
    url = normalize_database_url(database_url)
    kw: dict = {"pool_pre_ping": True}
    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        kw["poolclass"] = NullPool
    return create_engine(url, **kw)


def init_engine_and_tables(database_url: str) -> None:
    from app.db.models import Base

    eng = get_engine(database_url)
    Base.metadata.create_all(bind=eng)


def ping_database(database_url: str) -> None:
    eng = get_engine(database_url)
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
