"""Structured intake for persona discovery. No free-form questions: every field is validated.

A business describes a product or service; we never infer price, location or category silently.
`ProductIntake.validate()` returns a list of human-readable problems (empty = valid).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any

from .geography import Market, resolve_market

# category -> affordability profile (see affordability.PROFILES)
CATEGORIES: dict[str, str] = {
    "smartphone": "personal_durable",
    "computing": "personal_durable",
    "apparel_footwear": "personal_durable",
    "education_service": "personal_durable",
    "other": "personal_durable",
    "beauty_personal_care": "everyday",
    "food_beverage": "everyday",
    "health_wellness": "everyday",
    "digital_subscription": "subscription",
    "fintech_app": "subscription",
    "software_saas": "subscription",
    "home_appliance": "home_durable",
    "vehicle": "vehicle_property",
    "travel_hospitality": "experience",
    "entertainment_media": "experience",
}

PURCHASE_TYPES = ("one_off", "monthly", "annual", "repeat")
_CCY = re.compile(r"^[A-Z]{3}$")


@dataclass
class ProductIntake:
    name: str
    description: str
    category: str
    price: float
    currency: str
    location: str
    purchase_type: str = "one_off"
    purchases_per_year: float | None = None  # required when purchase_type == "repeat"
    country: str | None = None  # optional override; needed when the location is not a known city
    features: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    product_type: str = ""  # plain words for what it is, e.g. "toothpaste", "skin cream", "resume builder"; used to find competitors
    competitor_prices: list[float] = field(default_factory=list)  # same currency as `price`
    max_personas: int = 6
    gender_focus: str | None = None  # optional filter, applied after scoring
    age_focus: list[str] = field(default_factory=list)  # optional Qloo age buckets

    # ---- derived -------------------------------------------------------------------------------------------
    @property
    def market(self) -> Market | None:
        return resolve_market(self.location, self.country)

    @property
    def profile(self) -> str:
        return CATEGORIES.get(self.category, "personal_durable")

    @property
    def annual_cost(self) -> float:
        """What a buyer pays per year (price x frequency). Free products cost 0."""
        if self.purchase_type == "monthly":
            return self.price * 12
        if self.purchase_type == "repeat":
            return self.price * (self.purchases_per_year or 1)
        return self.price

    # ---- validation ----------------------------------------------------------------------------------------
    def validate(self) -> list[str]:
        errs: list[str] = []
        if not self.name or not self.name.strip():
            errs.append("name is required")
        if not self.description or len(self.description.strip()) < 10:
            errs.append("description is required (at least a sentence about what the product does)")
        if self.category not in CATEGORIES:
            errs.append(f"category must be one of: {', '.join(sorted(CATEGORIES))}")
        if not isinstance(self.price, (int, float)) or isinstance(self.price, bool) or self.price < 0:
            errs.append("price must be a number >= 0 (0 for free products)")
        if not _CCY.match((self.currency or "").upper()):
            errs.append("currency must be a 3-letter ISO code such as NGN, USD, JPY")
        if self.purchase_type not in PURCHASE_TYPES:
            errs.append(f"purchase_type must be one of: {', '.join(PURCHASE_TYPES)}")
        if self.purchase_type == "repeat" and not (self.purchases_per_year and self.purchases_per_year > 0):
            errs.append("purchases_per_year (> 0) is required when purchase_type is 'repeat'")
        if not self.location or not self.location.strip():
            errs.append("location is required")
        elif self.market is None:
            if self.country:
                errs.append(f"country {self.country!r} is not one of the supported markets")
            else:
                errs.append(f"cannot tell which country {self.location!r} is in: pass country (e.g. NG, US, JP)")
        if any((p is None or p <= 0) for p in self.competitor_prices):
            errs.append("competitor_prices must all be > 0")
        if not (1 <= int(self.max_personas) <= 10):
            errs.append("max_personas must be between 1 and 10")
        if self.gender_focus not in (None, "male", "female"):
            errs.append("gender_focus must be male, female or omitted")
        return errs

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["currency"] = (self.currency or "").upper()
        d["annual_cost"] = self.annual_cost
        m = self.market
        d["market"] = {"iso3": m.iso3, "name": m.name, "currency": m.currency} if m else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProductIntake":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kw = {k: v for k, v in d.items() if k in known}
        kw["currency"] = str(kw.get("currency", "")).upper()
        for key in ("features", "competitors", "competitor_prices", "age_focus"):
            if key in kw and kw[key] is None:
                kw[key] = []
        kw["features"] = [str(x).strip() for x in kw.get("features", []) if str(x).strip()]
        return cls(**kw)
