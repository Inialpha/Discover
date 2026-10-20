"""Minimal OpenAI-compatible chat client. Every exchange is saved to llm/NN_<name>.json (key never saved)."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from ...config import Settings
from ..recorder import RunRecorder


def extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON found in LLM output")
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start : end + 1])


class LLMError(RuntimeError):
    pass


def _limit_message(body: Any) -> str:
    try:
        return str(body["error"]["message"])[:160]
    except (KeyError, TypeError):
        return "rate limit"


def _is_daily_limit(body: Any) -> bool:
    """Groq style: "... on tokens per day (TPD): Limit 200000, Used 199705 ..." : waiting seconds will not help."""
    m = _limit_message(body).lower()
    return "per day" in m or "(tpd)" in m or "requests per day" in m


class LLMClient:
    def __init__(self, settings: Settings, recorder: RunRecorder, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.llm_configured:
            raise LLMError("LLM not configured (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)")
        self.s, self.rec, self._transport = settings, recorder, transport
        self.calls = 0
        self.models = [settings.llm_model, *[m for m in settings.llm_fallback_models if m != settings.llm_model]]
        self.exhausted: dict[str, str] = {}  # model -> provider message, once the DAY's token quota of that model is spent
        self.fallbacks_used = 0  # calls answered by a model other than the main one
        self.model_calls: dict[str, int] = {}
        self.max_wait = 30.0
        self._sleep = asyncio.sleep

    @property
    def daily_exhausted(self) -> str | None:
        """Set only when EVERY configured model has spent its daily quota: retrying is pointless."""
        if self.models and all(m in self.exhausted for m in self.models):
            return "; ".join(f"{m}: {msg}" for m, msg in self.exhausted.items())
        return None

    async def chat_json(self, name: str, system: str, user: str, temperature: float = 0.2, max_tokens: int = 2000) -> Any:
        """Tries the main model, then each fallback model, skipping any whose daily quota is spent. The first answer wins."""
        if self.daily_exhausted:
            raise LLMError(f"daily token limit reached ({self.daily_exhausted}); not calling the provider again this run")
        errors: list[str] = []
        for i, model in enumerate(self.models):
            if model in self.exhausted:
                continue
            try:
                out = await self._chat_with(model, name if i == 0 else f"{name}_fallback{i}", system, user, temperature, max_tokens)
            except LLMError as exc:
                errors.append(f"{model}: {exc}")
                continue
            self.model_calls[model] = self.model_calls.get(model, 0) + 1
            if i:
                self.fallbacks_used += 1
            return out
        raise LLMError("; ".join(errors) or "no model available")

    async def _chat_with(self, model: str, name: str, system: str, user: str, temperature: float, max_tokens: int) -> Any:
        payload: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        if self.s.llm_reasoning_effort:
            payload["reasoning_effort"] = self.s.llm_reasoning_effort
        headers = {"Authorization": f"Bearer {self.s.llm_api_key}"}
        record: dict[str, Any] = {"name": name, "request": {k: v for k, v in payload.items()}, "attempts": []}
        parsed: Any = None
        error: str | None = None
        async with httpx.AsyncClient(base_url=self.s.llm_base_url, timeout=self.s.llm_timeout, transport=self._transport) as http:
            for attempt in range(3):
                self.calls += 1
                try:
                    r = await http.post("/chat/completions", json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    record["attempts"].append({"error": f"{type(exc).__name__}: {exc}"})
                    error = str(exc)
                    continue
                entry: dict[str, Any] = {"status": r.status_code}
                try:
                    entry["json"] = r.json()
                except ValueError:
                    entry["text"] = r.text[:5000]
                record["attempts"].append(entry)
                if r.status_code == 400 and "response_format" in payload:
                    payload.pop("response_format")  # provider may not support JSON mode
                    continue
                if r.status_code == 400 and "reasoning_effort" in payload:
                    payload.pop("reasoning_effort")
                    continue
                if r.status_code == 429 and _is_daily_limit(entry.get("json")):
                    self.exhausted[model] = _limit_message(entry.get("json"))
                    error = f"daily token limit reached: {self.exhausted[model]}"
                    break
                if r.status_code >= 400:
                    error = f"HTTP {r.status_code}"
                    if r.status_code < 500 and r.status_code != 429:
                        break
                    if r.status_code == 429 and attempt < 2:
                        # token-per-minute limits: wait as the provider asks (capped), then retry
                        try:
                            wait = float(r.headers.get("retry-after", ""))
                        except ValueError:
                            wait = 10.0 * (attempt + 1)
                        entry["waited_s"] = min(wait, self.max_wait)
                        await self._sleep(min(wait, self.max_wait))
                    continue
                try:
                    choice = entry["json"]["choices"][0]
                    if choice.get("finish_reason") == "length":
                        payload["max_tokens"] = min(int(payload["max_tokens"] * 1.5), 6000)
                        error = "LLM output truncated (finish_reason=length); retrying with more tokens"
                        entry["note"] = error
                        continue
                    content = choice["message"]["content"]
                    parsed = extract_json(content)
                    error = None
                    break
                except (KeyError, IndexError, ValueError, TypeError) as exc:
                    error = f"unparseable LLM output: {exc}"
        record["error"] = error
        record["parsed"] = parsed
        self.rec.write_json(f"llm/{self.rec.next_seq():03d}_{name}.json", record)
        if parsed is None:
            raise LLMError(error or "LLM returned nothing")
        return parsed
