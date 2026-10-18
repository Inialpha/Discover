"""Daily exchange rates from open.er-api.com (free, no key; attribution required: https://www.exchangerate-api.com).

Response (verified live): {result:"success", provider, documentation, terms_of_use, time_last_update_utc,
time_next_update_utc, base_code:"USD", rates:{CODE: units per 1 USD}}. ~160 currencies including NGN, KES, ZAR.
Frankfurter/ECB was rejected because it has no NGN.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from .records import FX_PER_USD, RefRecord, now_iso

URL = "https://open.er-api.com/v6/latest/USD"
ATTRIBUTION = "Exchange rates by ExchangeRate-API (https://www.exchangerate-api.com)"


class FxError(RuntimeError):
    pass


class FxClient:
    def __init__(self, url: str = URL, timeout: float = 20.0, retries: int = 2,
                 transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep):
        self.url, self.retries, self.sleep = url, retries, sleep
        self._http = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": "discover-backend/0.1"})

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "FxClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def fetch(self, currencies: list[str] | None = None) -> list[RefRecord]:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self._http.get(self.url)
                if r.status_code >= 400:
                    raise FxError(f"HTTP {r.status_code}")
                return parse_rates(r.json(), currencies)
            except (FxError, httpx.TimeoutException, httpx.TransportError, ValueError) as e:
                last = e
                if attempt < self.retries:
                    self.sleep(0.6 * (attempt + 1))
        raise FxError(f"exchange rates: {last}")


def parse_rates(body: Any, currencies: list[str] | None = None) -> list[RefRecord]:
    if not isinstance(body, dict) or body.get("result") != "success" or not isinstance(body.get("rates"), dict):
        raise FxError("unexpected response shape or result != success")
    base = body.get("base_code", "USD")
    if base != "USD":
        raise FxError(f"expected USD base, got {base}")
    as_of = body.get("time_last_update_utc")
    fetched = now_iso()
    wanted = {c.upper() for c in currencies} if currencies else None
    out: list[RefRecord] = []
    for code, rate in body["rates"].items():
        if wanted is not None and code not in wanted:
            continue
        try:
            v = float(rate)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        out.append(RefRecord(country=code, indicator=FX_PER_USD, year=None, value=v, source="open.er-api.com",
                             fetched_at=fetched, as_of=as_of))
    return out


def convert(amount: float, from_ccy: str, to_ccy: str, per_usd: dict[str, float]) -> float:
    """Convert via USD using units-per-USD rates. Raises KeyError for a currency without a rate."""
    f, t = from_ccy.upper(), to_ccy.upper()
    if f == t:
        return float(amount)
    return float(amount) / per_usd[f] * per_usd[t]
