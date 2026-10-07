"""Async Qloo HTTP client.

Design goals (this is a *testing* harness first):
  * Every HTTP attempt is saved to the run folder with the exact params, status and raw body,
    so a failed run is as informative as a good one.
  * Parameter names that are not yet verified against the live API are expressed as ordered
    *variants*. The client tries the next variant when the API answers 400/422 and records which
    one worked, so one run teaches us the right spelling.
  * Bounded: global call budget, per-request timeout, limited retries with backoff.
  * The API key is sent as a header and never written to disk.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import Settings
from ..recorder import RunRecorder, slugify

_KEEP_HEADERS = ("content-type", "retry-after")


@dataclass
class Variant:
    """One concrete spelling of a request. `meta` is carried into the evidence for traceability."""

    params: dict[str, str]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class CallSpec:
    step: str
    label: str
    path: str
    variants: list[Variant]
    method: str = "GET"
    note: str = ""


@dataclass
class CallResult:
    spec: CallSpec
    ok: bool
    status: int | None = None
    body: Any = None
    variant_index: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    file: str | None = None
    files: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    error: str | None = None
    dry_run: bool = False
    skipped_reason: str | None = None


def _safe_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        k: v
        for k, v in headers.items()
        if k.lower() in _KEEP_HEADERS or k.lower().startswith(("x-ratelimit", "ratelimit"))
    }


def unwrap(body: Any) -> Any:
    """Some tooling wraps payloads as {"response": {...}}; accept both."""
    if isinstance(body, dict) and set(body.keys()) == {"response"}:
        return body["response"]
    return body


class QlooClient:
    def __init__(
        self,
        settings: Settings,
        recorder: RunRecorder,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        dry_run: bool = False,
        max_calls: int = 80,
        concurrency: int = 2,
        delay: float = 0.0,
        synthetic: bool = False,
    ):
        self.settings = settings
        self.rec = recorder
        self._transport = transport
        self.dry_run = dry_run
        self.max_calls = max_calls
        self.delay = delay
        self.synthetic = synthetic
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._http: httpx.AsyncClient | None = None
        self.calls_used = 0
        self.auth_failed = False
        self.results: list[CallResult] = []

    async def __aenter__(self) -> "QlooClient":
        headers = {"Accept": "application/json"}
        if self.settings.qloo_api_key:
            headers["X-Api-Key"] = self.settings.qloo_api_key
        self._http = httpx.AsyncClient(
            base_url=self.settings.qloo_base_url,
            headers=headers,
            timeout=httpx.Timeout(self.settings.qloo_timeout),
            transport=self._transport,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._http:
            await self._http.aclose()

    # ------------------------------------------------------------------ public

    async def call(self, spec: CallSpec) -> CallResult:
        async with self._sem:
            result = await self._call(spec)
        self.results.append(result)
        return result

    # ----------------------------------------------------------------- internal

    async def _call(self, spec: CallSpec) -> CallResult:
        if self.auth_failed:
            return CallResult(spec, False, skipped_reason="skipped: authentication failed earlier")
        if self.dry_run:
            return self._dry_run(spec)

        files: list[str] = []
        last: CallResult | None = None
        for index, variant in enumerate(spec.variants):
            if self.calls_used >= self.max_calls:
                reason = f"skipped: call budget of {self.max_calls} reached"
                return last or CallResult(spec, False, skipped_reason=reason, files=files)
            result = await self._attempt(spec, index, variant)
            files.append(result.file or "")
            result.files = [f for f in files if f]
            last = result
            if result.ok:
                return result
            if result.status == 401:
                self.auth_failed = True
                return result
            # Only a client error suggests "wrong parameter spelling": try the next variant.
            if result.status in (400, 422) and index + 1 < len(spec.variants):
                continue
            return result
        return last or CallResult(spec, False, error="no variants defined")

    def _dry_run(self, spec: CallSpec) -> CallResult:
        assert self._http is not None
        planned = []
        for variant in spec.variants:
            request = httpx.Request(spec.method, f"{self.settings.qloo_base_url}{spec.path}", params=variant.params)
            planned.append({"params": variant.params, "meta": variant.meta, "url": str(request.url)})
        rel = self.rec.write_json(
            f"qloo/{self.rec.next_seq():03d}_{spec.step}_{slugify(spec.label)}_DRYRUN.json",
            {
                "meta": {"step": spec.step, "label": spec.label, "dry_run": True, "note": spec.note},
                "planned_variants": planned,
            },
        )
        return CallResult(spec, False, file=rel, files=[rel], dry_run=True, skipped_reason="dry run")

    async def _attempt(self, spec: CallSpec, index: int, variant: Variant) -> CallResult:
        assert self._http is not None
        retries = self.settings.qloo_retries
        response: httpx.Response | None = None
        error: str | None = None
        started = time.perf_counter()
        for n in range(retries + 1):
            if self.delay:
                await asyncio.sleep(self.delay)
            self.calls_used += 1
            try:
                response = await self._http.request(spec.method, spec.path, params=variant.params)
                error = None
            except httpx.TimeoutException:
                response, error = None, "timeout"
            except httpx.HTTPError as exc:
                response, error = None, f"{type(exc).__name__}: {exc}"
            transient = response is None or response.status_code == 429 or response.status_code >= 500
            if transient and n < retries and self.calls_used < self.max_calls:
                wait = 2**n
                if response is not None:
                    try:
                        wait = float(response.headers.get("retry-after", wait))
                    except ValueError:
                        pass
                await asyncio.sleep(min(wait, 20))
                continue
            break
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        body: Any = None
        text: str | None = None
        status: int | None = None
        full_url: str | None = None
        resp_headers: dict[str, str] = {}
        if response is not None:
            status = response.status_code
            full_url = str(response.request.url)
            resp_headers = _safe_headers(response.headers)
            try:
                body = response.json()
            except ValueError:
                text = response.text[:20000]
                if 200 <= status < 300:
                    error = "response was not JSON"
        else:
            full_url = str(httpx.Request(spec.method, f"{self.settings.qloo_base_url}{spec.path}", params=variant.params).url)

        ok = status is not None and 200 <= status < 300 and body is not None
        if ok and isinstance(unwrap(body), dict) and unwrap(body).get("success") is False:
            ok, error = False, "API returned success=false"
        if status is not None and not ok and error is None:
            error = f"HTTP {status}"

        rel = self.rec.write_json(
            f"qloo/{self.rec.next_seq():03d}_{spec.step}_{slugify(spec.label)}_v{index + 1}.json",
            {
                "meta": {
                    "step": spec.step,
                    "label": spec.label,
                    "variant_index": index,
                    "variant_meta": variant.meta,
                    "note": spec.note,
                    "synthetic": self.synthetic,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "elapsed_ms": elapsed_ms,
                    "http_requests_made": n + 1,
                },
                "request": {
                    "method": spec.method,
                    "base_url": self.settings.qloo_base_url,
                    "path": spec.path,
                    "params": variant.params,
                    "full_url": full_url,
                    "headers": {"X-Api-Key": "***redacted***" if self.settings.qloo_api_key else "(none)"},
                },
                "response": {"status": status, "headers": resp_headers, "json": body, "text": text},
                "error": error,
            },
        )
        return CallResult(
            spec,
            ok,
            status=status,
            body=unwrap(body) if ok else body,
            variant_index=index,
            meta=dict(variant.meta),
            file=rel,
            elapsed_ms=elapsed_ms,
            error=error,
        )
