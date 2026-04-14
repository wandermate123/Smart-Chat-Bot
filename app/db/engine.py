import os
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


@lru_cache(maxsize=4)
def get_engine(database_url: str):
    kw: dict = {"pool_pre_ping": True}
    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
        kw["poolclass"] = NullPool
    return create_engine(database_url, **kw)


def init_engine_and_tables(database_url: str) -> None:
    from app.db.models import Base

    eng = get_engine(database_url)
    Base.metadata.create_all(bind=eng)


def ping_database(database_url: str) -> None:
    eng = get_engine(database_url)
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
