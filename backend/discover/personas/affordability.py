"""Affordability: how big is this product's yearly cost relative to local income?

Everything here is arithmetic on cited reference data plus explicit threshold tables. The tier names describe
affordability *relative to local income* (budget / mass / upper / premium); none of them is the default.
The thresholds are documented assumptions (rules of thumb), kept in one table so they can be reviewed and changed.

ratio      = annual product cost / GNI per capita (both in local currency; no FX needed for a local price)
tier       = ratio against the profile's boundaries  (< b1 budget, < b2 mass, < b3 upper, else premium)
quintile q = annual cost / (income share of that 20% x 5 x GNI per capita)   (survey-based, sparse, country level)
reach      = comfortable if quintile ratio <= b2, stretch if <= b3, else out_of_reach
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from .intake import ProductIntake
from .refdata.fx import convert
from .refdata.records import GNI_PC_LCU, QUINTILE_SHARES, RefRecord
from .refdata.store import ReferenceStore, age_days

TIERS = ("budget", "mass", "upper", "premium")


@dataclass(frozen=True)
class Profile:
    name: str
    boundaries: tuple[float, float, float]  # b1, b2, b3 as a share of annual income
    blurb: str


PROFILES: dict[str, Profile] = {p.name: p for p in (
    Profile("everyday", (0.002, 0.01, 0.03), "small, frequent purchases (food, personal care, wellness)"),
    Profile("personal_durable", (0.03, 0.15, 0.40), "personal devices, clothing, courses"),
    Profile("home_durable", (0.05, 0.20, 0.50), "household appliances and larger electronics"),
    Profile("subscription", (0.005, 0.02, 0.06), "recurring digital services, judged on the yearly total"),
    Profile("experience", (0.01, 0.05, 0.15), "travel, hospitality, entertainment"),
    Profile("vehicle_property", (0.5, 1.5, 4.0), "vehicles and other very large purchases"),
)}


class ReferenceDataMissing(RuntimeError):
    """A needed statistic is not in the snapshot or cache. Run `discover refdata refresh`."""


@dataclass
class QuintileReach:
    quintile: int
    income_share_pct: float | None
    share_year: int | None
    annual_income_lcu: float | None
    ratio: float | None
    reach: str  # comfortable | stretch | out_of_reach | unknown


@dataclass
class Affordability:
    country: str
    country_name: str
    local_currency: str
    entered_price: float
    entered_currency: str
    local_price: float
    local_annual_cost: float
    conversion: dict[str, Any] | None
    gni_per_capita_lcu: float
    gni_year: int | None
    ratio: float
    tier: str
    profile: str
    boundaries: tuple[float, float, float]
    quintiles: list[QuintileReach]
    quintile_data: str  # complete | partial | none
    market_position: dict[str, Any] | None
    caveats: list[str] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)

    def reach_of(self, q: int) -> str:
        for x in self.quintiles:
            if x.quintile == q:
                return x.reach
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["quintiles"] = [q.__dict__ for q in self.quintiles]
        d["boundaries"] = list(self.boundaries)
        return d


def tier_for(ratio: float, boundaries: tuple[float, float, float]) -> str:
    b1, b2, b3 = boundaries
    if ratio < b1:
        return "budget"
    if ratio < b2:
        return "mass"
    if ratio < b3:
        return "upper"
    return "premium"


def reach_for(ratio: float, boundaries: tuple[float, float, float]) -> str:
    _, b2, b3 = boundaries
    if ratio <= b2:
        return "comfortable"
    if ratio <= b3:
        return "stretch"
    return "out_of_reach"


def market_position(price: float, competitor_prices: list[float]) -> dict[str, Any] | None:
    if not competitor_prices:
        return None
    med = statistics.median(competitor_prices)
    r = price / med
    pos = "below" if r < 0.85 else "above" if r > 1.15 else "in_line"
    return {"competitor_median": med, "n": len(competitor_prices), "price_vs_median": round(r, 3), "position": pos}


def assess(intake: ProductIntake, store: ReferenceStore, fx_max_age_days: float = 7.0) -> Affordability:
    market = intake.market
    if market is None:
        raise ValueError("intake has no resolvable market; validate() first")
    caveats: list[str] = []
    inputs: list[dict[str, Any]] = []

    gni = store.latest(market.iso3, GNI_PC_LCU)
    if gni is None:
        raise ReferenceDataMissing(f"no GNI per capita (local currency) for {market.iso3}; run `discover refdata refresh`")
    inputs.append(gni.cite())

    # price in local currency
    entered_ccy = intake.currency.upper()
    conversion: dict[str, Any] | None = None
    local_price = float(intake.price)
    if entered_ccy != market.currency:
        rates = store.fx_rates()
        missing = [c for c in (entered_ccy, market.currency) if c not in rates]
        if missing:
            raise ReferenceDataMissing(f"no exchange rate for {', '.join(missing)}; run `discover refdata refresh`")
        local_price = convert(intake.price, entered_ccy, market.currency, {c: r.value for c, r in rates.items()})
        used = [rates[entered_ccy], rates[market.currency]]
        inputs += [u.cite() for u in used]
        conversion = {"from": entered_ccy, "to": market.currency, "rates_per_usd": {u.country: u.value for u in used},
                      "as_of": [u.as_of for u in used if u.as_of], "source": used[0].source}
        old = [age_days(u.fetched_at) for u in used]
        if any(a is not None and a > fx_max_age_days for a in old):
            caveats.append(f"exchange rate is older than {fx_max_age_days:g} days; refresh before relying on the conversion")
        caveats.append(f"price converted from {entered_ccy} to {market.currency}; enter the local price for a more exact result")

    profile = PROFILES[intake.profile]
    annual_local = local_price * (intake.annual_cost / intake.price) if intake.price else 0.0
    ratio = annual_local / gni.value
    tier = tier_for(ratio, profile.boundaries) if annual_local > 0 else "budget"
    if annual_local == 0:
        caveats.append("free product: affordability is not a barrier, so every segment is treated as comfortable")

    # income quintiles (sparse, survey-based)
    quintiles: list[QuintileReach] = []
    found = 0
    years: set[int] = set()
    shares_total = 0.0
    for q, ind in QUINTILE_SHARES.items():
        rec: RefRecord | None = store.latest(market.iso3, ind)
        if rec is None:
            quintiles.append(QuintileReach(q, None, None, None, None, "unknown"))
            continue
        found += 1
        shares_total += rec.value
        if rec.year:
            years.add(rec.year)
        inputs.append(rec.cite())
        income = rec.value / 100.0 * 5.0 * gni.value
        qr = annual_local / income if income > 0 else None
        reach = "comfortable" if annual_local == 0 else (reach_for(qr, profile.boundaries) if qr is not None else "unknown")
        quintiles.append(QuintileReach(q, rec.value, rec.year, income, qr, reach))
    quintile_data = "complete" if found == 5 else "partial" if found else "none"
    if quintile_data == "none":
        caveats.append("no income-distribution data for this country: affordability uses the country average only, "
                       "so segments are ranked on rules and features without an income-band check")
    elif quintile_data == "partial":
        caveats.append(f"income distribution is only available for {found} of 5 income bands")
    if quintile_data == "complete":
        if abs(shares_total - 100.0) > 3.0:
            caveats.append(f"income shares sum to {shares_total:.1f}%, not ~100%: treat income-band results with care")
        if len(years) > 1:
            caveats.append(f"income-band surveys come from different years ({sorted(years)})")
    if quintile_data != "none":
        yr = max(years) if years else None
        caveats.append(f"income-band figures are national averages from household surveys{f' (latest {yr})' if yr else ''}; "
                       "they approximate, not measure, what a household spends on this product")
    caveats.append("GNI per capita is a national average, not city or household disposable income")

    return Affordability(
        country=market.iso3, country_name=market.name, local_currency=market.currency, entered_price=intake.price,
        entered_currency=entered_ccy, local_price=local_price, local_annual_cost=annual_local, conversion=conversion,
        gni_per_capita_lcu=gni.value, gni_year=gni.year, ratio=ratio, tier=tier, profile=profile.name,
        boundaries=profile.boundaries, quintiles=quintiles, quintile_data=quintile_data,
        market_position=market_position(intake.price, intake.competitor_prices), caveats=caveats, inputs=inputs)
