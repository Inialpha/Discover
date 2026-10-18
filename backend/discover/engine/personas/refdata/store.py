"""Reference data store: shipped snapshot + writable cache + optional live refresh.

Lookup order for `latest()`: every record from snapshot and cache is merged (cache overrides the snapshot for
the same country/indicator/year); the record with the highest year wins (FX: newest fetched_at). The persona
engine only ever reads through this class, so it cannot tell a live value from a cached one except by the
`source` / `fetched_at` fields that are carried into every report.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fx import FxClient, FxError
from .records import CORE_INDICATORS, FX_PER_USD, RefRecord
from .worldbank import WorldBankClient, WorldBankError

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "reference_snapshot.json"
DEFAULT_CACHE = Path(".discover_cache") / "reference.json"


def _load(path: Path) -> list[RefRecord]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for d in data.get("records", []) if isinstance(data, dict) else []:
        try:
            out.append(RefRecord.from_dict(d))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def age_days(fetched_at: str, now: datetime | None = None) -> float | None:
    try:
        t = datetime.fromisoformat(fetched_at)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - t).total_seconds() / 86400


class ReferenceStore:
    def __init__(self, cache_path: Path | None = DEFAULT_CACHE, snapshot_path: Path | None = SNAPSHOT_PATH):
        self.cache_path = cache_path
        self._snapshot = _load(snapshot_path) if snapshot_path else []
        self._cache = _load(cache_path) if cache_path else []

    # ---- reading ----------------------------------------------------------------------------------------
    def _merged(self) -> dict[tuple, RefRecord]:
        m: dict[tuple, RefRecord] = {}
        for r in self._snapshot:
            m[r.key()] = r
        for r in self._cache:
            m[r.key()] = r
        return m

    def series(self, country: str, indicator: str) -> list[RefRecord]:
        rows = [r for k, r in self._merged().items() if k[0] == country and k[1] == indicator]
        return sorted(rows, key=lambda r: (r.year is None, -(r.year or 0)))

    def latest(self, country: str, indicator: str) -> RefRecord | None:
        rows = self.series(country, indicator)
        if not rows:
            return None
        if all(r.year is None for r in rows):  # FX: newest fetch wins
            return max(rows, key=lambda r: r.fetched_at)
        return rows[0]

    def fx_rates(self) -> dict[str, RefRecord]:
        best: dict[str, RefRecord] = {}
        for r in self._merged().values():
            if r.indicator == FX_PER_USD and (r.country not in best or r.fetched_at > best[r.country].fetched_at):
                best[r.country] = r
        return best

    def per_usd(self) -> dict[str, float]:
        return {c: r.value for c, r in self.fx_rates().items()}

    # ---- writing ----------------------------------------------------------------------------------------
    def put_many(self, records: list[RefRecord]) -> None:
        index = {r.key(): i for i, r in enumerate(self._cache)}
        for r in records:
            if r.key() in index:
                self._cache[index[r.key()]] = r
            else:
                index[r.key()] = len(self._cache)
                self._cache.append(r)

    def save(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps({"records": [r.to_dict() for r in self._cache]}, indent=1), encoding="utf-8")

    # ---- live refresh -----------------------------------------------------------------------------------
    def refresh(self, countries: list[str], currencies: list[str], wb: WorldBankClient | None = None,
                fx: FxClient | None = None, indicators: list[str] | None = None) -> dict[str, Any]:
        """Fetch live data into the cache. Never raises: failures are listed in the report."""
        report: dict[str, Any] = {"fetched": 0, "failed": [], "empty": []}
        own_wb, own_fx = wb is None, fx is None
        wb = wb or WorldBankClient()
        fx = fx or FxClient()
        try:
            for ind in indicators or CORE_INDICATORS:
                try:
                    recs = wb.fetch(countries, ind)
                except WorldBankError as e:
                    report["failed"].append({"indicator": ind, "error": str(e)})
                    continue
                got = {r.country for r in recs}
                report["empty"] += [{"indicator": ind, "country": c} for c in countries if c not in got]
                self.put_many(recs)
                report["fetched"] += len(recs)
            try:
                recs = fx.fetch(sorted(set(currencies) | {"USD"}))
                self.put_many(recs)
                report["fetched"] += len(recs)
            except FxError as e:
                report["failed"].append({"indicator": FX_PER_USD, "error": str(e)})
        finally:
            if own_wb:
                wb.close()
            if own_fx:
                fx.close()
        self.save()
        return report
