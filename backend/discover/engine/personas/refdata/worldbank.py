"""World Bank Indicators API client (free, no key). https://api.worldbank.org/v2/

Response shape (verified live): a 2-element JSON array [metadata, records]. Each record has
`indicator{id,value}`, `country{id,value}`, `countryiso3code`, `date` (year string), `value` (number or null).
When a query matches nothing, the second element is null; errors come back as [{"message":[...]}].
"""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from .records import RefRecord, now_iso

BASE = "https://api.worldbank.org/v2"


class WorldBankError(RuntimeError):
    pass


class WorldBankClient:
    def __init__(self, base_url: str = BASE, timeout: float = 20.0, retries: int = 2,
                 transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep):
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.sleep = sleep
        self._http = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": "discover-backend/0.1"})

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "WorldBankClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def fetch(self, countries: list[str], indicator: str, recent: int = 5) -> list[RefRecord]:
        """Most recent `recent` yearly values (nulls dropped) for each country (ISO3)."""
        url = f"{self.base_url}/country/{';'.join(countries)}/indicator/{indicator}"
        params = {"format": "json", "mrv": str(recent), "per_page": "1000"}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self._http.get(url, params=params)
                if r.status_code >= 500 or r.status_code == 429:
                    raise WorldBankError(f"HTTP {r.status_code}")
                if r.status_code >= 400:
                    raise WorldBankError(f"HTTP {r.status_code}: {r.text[:200]}")
                return parse_records(r.json(), indicator)
            except WorldBankError as e:
                last = e
                if "HTTP 4" in str(e) and "429" not in str(e):
                    break  # client error: retrying will not help
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as e:
                last = e
            if attempt < self.retries:
                self.sleep(0.6 * (attempt + 1))
        raise WorldBankError(f"{indicator} for {','.join(countries)}: {last}")


def parse_records(body: Any, indicator: str) -> list[RefRecord]:
    if not isinstance(body, list) or not body:
        raise WorldBankError("unexpected response shape")
    if len(body) == 1:
        msg = body[0].get("message") if isinstance(body[0], dict) else None
        raise WorldBankError(f"API message: {msg}")
    rows = body[1]
    if rows is None:
        return []
    fetched = now_iso()
    out: list[RefRecord] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("value") is None:
            continue
        iso3 = row.get("countryiso3code") or (row.get("country") or {}).get("id")
        try:
            year = int(row["date"])
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if not iso3:
            continue
        out.append(RefRecord(country=iso3, indicator=indicator, year=year, value=value, source="worldbank", fetched_at=fetched))
    return out
