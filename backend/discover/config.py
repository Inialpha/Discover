"""Environment-driven settings. No secrets are ever written to run output."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Hackathon keys only work against this host (see docs/07-qloo/market-discovery-workflow-reference.md).
DEFAULT_QLOO_BASE_URL = "https://hackathon.api.qloo.com"


def load_dotenv(start: Path | None = None) -> Path | None:
    """Minimal .env loader (no dependency). Never overrides variables already set.

    Looks in the start directory and up to three parents. Empty values are ignored so
    that defaults still apply.
    """
    start = (start or Path.cwd()).resolve()
    for directory in [start, *list(start.parents)[:3]]:
        env_file = directory / ".env"
        if not env_file.is_file():
            continue
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value
        return env_file
    return None


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    qloo_api_key: str | None
    qloo_base_url: str
    qloo_timeout: float
    qloo_retries: int
    llm_api_key: str | None
    llm_base_url: str | None
    llm_model: str | None
    llm_timeout: float
    llm_max_input_chars: int = 9000
    llm_max_output_tokens: int = 3500
    llm_reasoning_effort: str | None = None

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            qloo_api_key=os.environ.get("QLOO_API_KEY") or None,
            qloo_base_url=(os.environ.get("QLOO_BASE_URL") or DEFAULT_QLOO_BASE_URL).rstrip("/"),
            qloo_timeout=_float("QLOO_TIMEOUT_SECONDS", 45.0),
            qloo_retries=_int("QLOO_RETRIES", 2),
            llm_api_key=os.environ.get("LLM_API_KEY") or None,
            llm_base_url=(os.environ.get("LLM_BASE_URL") or "").rstrip("/") or None,
            llm_model=os.environ.get("LLM_MODEL") or None,
            llm_timeout=_float("LLM_TIMEOUT_SECONDS", 90.0),
            llm_max_input_chars=_int("LLM_MAX_INPUT_CHARS", 9000),
            llm_max_output_tokens=_int("LLM_MAX_OUTPUT_TOKENS", 3500),
            llm_reasoning_effort=os.environ.get("LLM_REASONING_EFFORT") or None,
        )
