"""Alembic environment — uses DATABASE_URL from the environment."""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import create_engine, pool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.db.engine import normalize_database_url, resolve_database_url_from_env
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    # Does not import app Settings (Meta vars not required to run migrations).
    url = resolve_database_url_from_env()
    if not url:
        raise RuntimeError(
            "No database URL: set DATABASE_URL, or DATABASE_HOST and DATABASE_PASSWORD "
            "(recommended if your password contains @ # ] and breaks a single URI)."
        )
    return normalize_database_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Use create_engine(get_url()) so postgresql+psycopg:// (psycopg v3) is honored.
    # A plain postgresql:// URL would pull in psycopg2, which this project does not use.
    connectable = create_engine(get_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
