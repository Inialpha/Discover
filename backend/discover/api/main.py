"""FastAPI app. Run: uvicorn discover.api.main:app --reload   (see backend/.env.example for the environment)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import load_dotenv
from . import migrations
from .db import make_engine, make_session_factory
from .routes import admin, analyses, auth, exports, meta, products
from .services import runner
from .services.runner import fail_stale
from .settings import ApiSettings


def create_app(settings: ApiSettings | None = None, engine_kwargs: dict[str, Any] | None = None) -> FastAPI:
    load_dotenv()
    st = settings or ApiSettings.from_env()
    engine = make_engine(st.database_url)
    sf = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if st.auto_migrate:  # Alembic: creates a new database, or upgrades an existing one without losing data
            async with engine.begin() as conn:
                await conn.run_sync(migrations.upgrade)
        await fail_stale(sf)
        try:
            yield
        finally:
            await runner.cancel_all()  # stop background runs cleanly on shutdown
            await engine.dispose()

    app = FastAPI(title="Discover API", version="0.1.0", lifespan=lifespan)
    app.state.settings, app.state.session_factory, app.state.engine = st, sf, engine
    app.state.engine_kwargs = engine_kwargs or {}  # tests inject fake LLM/Qloo transports here
    app.add_middleware(CORSMiddleware, allow_origins=st.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    for r in (meta.router, auth.router, analyses.router, products.router, exports.router, admin.router):
        app.include_router(r)
    return app


def __getattr__(name: str):  # `uvicorn discover.api.main:app` builds the app lazily so importing this module has no side effects
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)
