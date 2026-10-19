"""Async SQLAlchemy. SQLite (aiosqlite) for development and tests, Postgres (asyncpg) in production (Neon, Supabase, Aiven...).

asyncpg is used rather than psycopg because it works on every event loop, including Windows' default one.
"""

from __future__ import annotations

from typing import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# libpq-style options that asyncpg does not understand, or that are spelled differently
_DROP = {"channel_binding", "options", "target_session_attrs", "application_name"}


def normalize_url(url: str) -> str:
    """Hosts hand out postgres:// or postgresql:// URLs (with ?sslmode=require); turn them into SQLAlchemy asyncpg URLs."""
    if url.startswith("sqlite:"):
        return "sqlite+aiosqlite:" + url[len("sqlite:"):]
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") or url.startswith("postgresql+psycopg://"):
        url = "postgresql+asyncpg://" + url.split("://", 1)[1]
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        q = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k in _DROP:
                continue
            if k == "sslmode":  # asyncpg spells it "ssl"
                k = "ssl"
                if v in ("disable", "allow"):
                    continue
                v = "require" if v in ("prefer", "require", "verify-ca", "verify-full") else v
            q.append((k, v))
        return urlunsplit(parts._replace(query=urlencode(q)))
    return url


def make_engine(url: str) -> AsyncEngine:
    url = normalize_url(url)
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool
        kw: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url.endswith("sqlite+aiosqlite://"):
            kw["poolclass"] = StaticPool
        return create_async_engine(url, **kw)
    # statement_cache_size=0 keeps asyncpg working behind PgBouncer-style poolers (Neon's "-pooler" hosts, Supabase)
    return create_async_engine(url, pool_pre_ping=True, pool_recycle=300,
                               connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0})


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as db:
        yield db
