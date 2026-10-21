"""API settings, all from environment variables (see backend/.env.example). The engine reads its own (QLOO_*, LLM_*, AGENT_LLM_*)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None or v == "" else v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class ApiSettings:
    env: str  # development | production
    database_url: str
    secret_key: str
    cors_origins: list[str]
    token_minutes: int
    max_runs_per_day: int
    allow_signup: bool
    mock_engine: bool  # run analyses against the offline mock Qloo/LLM (demos without keys)
    runs_dir: str
    agent_enabled: bool
    llm_delay: float  # seconds between LLM calls (provider token-per-minute limits, e.g. 8 on Groq's free tier)
    engine_mode: str = "lean"  # lean = few shared Qloo calls (about 12); full = every segment gets its own calls (about 50)
    max_qloo_calls: int = 0  # ceiling on Qloo calls per analysis; 0 = the mode's default (30 lean, 150 full)
    auto_migrate: bool = True  # apply pending Alembic migrations when the API starts
    keep_runs: bool = False  # keep every run's folder (calls, model exchanges, evidence, ledger) under RUNS_DIR for debugging

    @classmethod
    def from_env(cls) -> "ApiSettings":
        env = (os.environ.get("APP_ENV") or "development").lower()
        key = os.environ.get("SECRET_KEY") or ""
        if not key:
            if env == "production":
                raise RuntimeError("SECRET_KEY must be set in production")
            key = secrets.token_urlsafe(32)  # dev only: tokens stop working after a restart
        return cls(
            env=env,
            database_url=os.environ.get("DATABASE_URL") or "sqlite:///./discover.db",
            secret_key=key,
            cors_origins=[o.strip() for o in (os.environ.get("CORS_ORIGINS") or "http://localhost:5173").split(",") if o.strip()],
            token_minutes=_int("TOKEN_MINUTES", 60 * 24 * 7),
            max_runs_per_day=_int("MAX_RUNS_PER_DAY", 10),
            allow_signup=_bool("ALLOW_SIGNUP", True),
            mock_engine=_bool("DISCOVER_MOCK", False),
            runs_dir=os.environ.get("RUNS_DIR") or "/tmp/discover-runs",
            agent_enabled=_bool("AGENT_ENABLED", True),
            llm_delay=float(os.environ.get("LLM_DELAY_SECONDS") or 0),
            keep_runs=_bool("KEEP_RUNS", False),
            auto_migrate=_bool("AUTO_MIGRATE", True),
            engine_mode="full" if (os.environ.get("ENGINE_MODE") or "").strip().lower() == "full" else "lean",
            max_qloo_calls=_int("MAX_QLOO_CALLS", 0),
        )
