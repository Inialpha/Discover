"""Minimal OpenAI-compatible chat client. Every exchange is saved to llm/NN_<name>.json (key never saved)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import Settings
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


class LLMClient:
    def __init__(self, settings: Settings, recorder: RunRecorder, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.llm_configured:
            raise LLMError("LLM not configured (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)")
        self.s, self.rec, self._transport = settings, recorder, transport
        self.calls = 0

    async def chat_json(self, name: str, system: str, user: str, temperature: float = 0.2, max_tokens: int = 2000) -> Any:
        payload: dict[str, Any] = {
            "model": self.s.llm_model,
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
                if r.status_code >= 400:
                    error = f"HTTP {r.status_code}"
                    if r.status_code < 500 and r.status_code != 429:
                        break
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
