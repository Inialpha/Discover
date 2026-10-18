"""Markets we can reason about: country codes, local currency, and a small city -> country map.

This is static reference data (identifiers, not statistics). It only lets us turn "Lagos" into NGA/NGN so the
right World Bank series and currency are used. Unknown places are NOT guessed: the caller must pass a country.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    iso2: str
    iso3: str
    name: str
    currency: str  # ISO 4217 local currency


MARKETS: dict[str, Market] = {m.iso3: m for m in (
    Market("US", "USA", "United States", "USD"),
    Market("GB", "GBR", "United Kingdom", "GBP"),
    Market("JP", "JPN", "Japan", "JPY"),
    Market("IN", "IND", "India", "INR"),
    Market("NG", "NGA", "Nigeria", "NGN"),
    Market("KE", "KEN", "Kenya", "KES"),
    Market("ZA", "ZAF", "South Africa", "ZAR"),
    Market("BR", "BRA", "Brazil", "BRL"),
    Market("DE", "DEU", "Germany", "EUR"),
    Market("AE", "ARE", "United Arab Emirates", "AED"),
)}

_BY_ISO2 = {m.iso2: m for m in MARKETS.values()}
_BY_NAME = {m.name.lower(): m for m in MARKETS.values()}
_ALIASES = {"usa": "USA", "us": "USA", "uk": "GBR", "britain": "GBR", "england": "GBR", "uae": "ARE", "emirates": "ARE",
            "deutschland": "DEU", "america": "USA"}

# city (lowercase) -> iso3. Deliberately short; extend as markets are added.
CITIES: dict[str, str] = {
    "new york": "USA", "new york city": "USA", "nyc": "USA", "los angeles": "USA", "chicago": "USA", "san francisco": "USA",
    "houston": "USA", "atlanta": "USA", "miami": "USA",
    "london": "GBR", "manchester": "GBR", "birmingham": "GBR",
    "tokyo": "JPN", "osaka": "JPN", "kyoto": "JPN",
    "mumbai": "IND", "delhi": "IND", "new delhi": "IND", "bangalore": "IND", "bengaluru": "IND", "hyderabad": "IND",
    "lagos": "NGA", "abuja": "NGA", "port harcourt": "NGA", "ibadan": "NGA", "kano": "NGA", "uyo": "NGA",
    "nairobi": "KEN", "mombasa": "KEN",
    "johannesburg": "ZAF", "cape town": "ZAF", "durban": "ZAF",
    "sao paulo": "BRA", "são paulo": "BRA", "rio de janeiro": "BRA",
    "berlin": "DEU", "munich": "DEU", "hamburg": "DEU",
    "dubai": "ARE", "abu dhabi": "ARE",
}


def resolve_market(location: str | None, country: str | None = None) -> Market | None:
    """Country wins when given (ISO2, ISO3, name or alias). Otherwise the last comma part of the location is tried
    as a country, then the first part as a city. Returns None when unknown (never guesses)."""
    for raw in (country,):
        m = _lookup_country(raw)
        if m:
            return m
        if raw:
            return None  # an explicit but unknown country is an error for the caller, not something to override
    if not location:
        return None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    for p in reversed(parts):
        m = _lookup_country(p)
        if m:
            return m
    for p in parts:
        iso3 = CITIES.get(p.lower())
        if iso3:
            return MARKETS[iso3]
    return None


def _lookup_country(raw: str | None) -> Market | None:
    if not raw:
        return None
    k = raw.strip().lower()
    if k in _ALIASES:
        return MARKETS[_ALIASES[k]]
    if k.upper() in MARKETS:
        return MARKETS[k.upper()]
    if k.upper() in _BY_ISO2:
        return _BY_ISO2[k.upper()]
    return _BY_NAME.get(k)
