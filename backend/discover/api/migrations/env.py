"""Alembic environment. Works with the app's async engine (asyncpg / aiosqlite) and with a connection handed in by the app."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from discover.api import models  # noqa: F401  (registers the tables on Base.metadata)
from discover.api.db import Base, normalize_url
from discover.api.settings import ApiSettings

cfg = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                      render_as_batch=connection.dialect.name == "sqlite")  # SQLite cannot ALTER most things: batch mode rebuilds the table


def _run(connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    url = normalize_url(ApiSettings.from_env().database_url)
    engine = async_engine_from_config({"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


def run_migrations_online() -> None:
    existing = cfg.attributes.get("connection")
    if existing is not None:  # the app is migrating at startup, on its own connection
        _run(existing)
    else:  # the alembic command line
        asyncio.run(_run_async())


def run_migrations_offline() -> None:
    context.configure(url=normalize_url(ApiSettings.from_env().database_url), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
