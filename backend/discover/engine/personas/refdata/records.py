"""One record shape for every reference statistic, whatever its source (live API, cache or shipped snapshot)."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

# World Bank indicator codes
GNI_PC_LCU = "NY.GNP.PCAP.CN"          # GNI per capita, current local currency units
GNI_PC_PPP = "NY.GNP.PCAP.PP.CD"       # GNI per capita, PPP (current international $)
OFFICIAL_FX = "PA.NUS.FCRF"            # official exchange rate, LCU per US$, period average
QUINTILE_SHARES = {                    # income share held by each 20% of the population (survey-based, sparse)
    1: "SI.DST.FRST.20",
    2: "SI.DST.02ND.20",
    3: "SI.DST.03RD.20",
    4: "SI.DST.04TH.20",
    5: "SI.DST.05TH.20",
}
FX_PER_USD = "FX.LCU_PER_USD"          # live daily rate (record.country holds the currency code)

CORE_INDICATORS = [GNI_PC_LCU, GNI_PC_PPP, OFFICIAL_FX, *QUINTILE_SHARES.values()]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class RefRecord:
    country: str                 # ISO3 for World Bank series; ISO 4217 code for FX records
    indicator: str
    year: int | None
    value: float
    source: str                  # "worldbank" | "open.er-api.com" | "snapshot"
    fetched_at: str
    as_of: str | None = None     # provider's own timestamp (FX)
    note: str | None = None

    def key(self) -> tuple[str, str, int | None]:
        return (self.country, self.indicator, self.year)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RefRecord":
        return cls(country=d["country"], indicator=d["indicator"], year=d.get("year"), value=float(d["value"]),
                   source=d.get("source", "unknown"), fetched_at=d.get("fetched_at", ""), as_of=d.get("as_of"),
                   note=d.get("note"))

    def cite(self) -> dict[str, Any]:
        """Compact provenance block shown in reports."""
        return {"indicator": self.indicator, "country": self.country, "year": self.year, "value": self.value,
                "source": self.source, "fetched_at": self.fetched_at, **({"as_of": self.as_of} if self.as_of else {})}
