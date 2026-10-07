"""Age/gender vocabulary. Bucket names come from the Qloo workflow transcript (unverified against
the live API) and are isolated here so a correction touches one file."""

from __future__ import annotations

import re

# (name, lowest age, highest age)
AGE_BUCKETS: list[tuple[str, int, int]] = [
    ("24_and_younger", 0, 24),
    ("25_to_29", 25, 29),
    ("30_to_34", 30, 34),
    ("35_to_44", 35, 44),
    ("45_to_54", 45, 54),
    ("55_and_older", 55, 120),
]
BUCKET_NAMES = [b[0] for b in AGE_BUCKETS]


def age_range_to_buckets(lo: int | None, hi: int | None, min_overlap: int = 2) -> list[str]:
    """Buckets overlapping [lo, hi]. '25 to 35' -> 25_to_29, 30_to_34 (35_to_44 overlaps by 1 year)."""
    if lo is None and hi is None:
        return []
    lo = 0 if lo is None else lo
    hi = 120 if hi is None else hi
    if lo > hi:
        lo, hi = hi, lo
    out = []
    for name, b_lo, b_hi in AGE_BUCKETS:
        overlap = min(hi, b_hi) - max(lo, b_lo) + 1
        inside = lo >= b_lo and hi <= b_hi
        if overlap >= min_overlap or (overlap > 0 and inside):
            out.append(name)
    return out


def bucket_range(name: str) -> tuple[int, int] | None:
    for n, lo, hi in AGE_BUCKETS:
        if n == name:
            return lo, hi
    return None


def parse_age_text(text: str) -> tuple[int | None, int | None]:
    """'25-35', '25 to 35', '30', '25+' -> (lo, hi)."""
    t = text.strip().lower()
    m = re.search(r"(\d{1,3})\s*(?:to|-|–|—|and)\s*(\d{1,3})", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,3})\s*\+", t) or re.search(r"(?:over|above|older than)\s*(\d{1,3})", t)
    if m:
        return int(m.group(1)), None
    m = re.search(r"(?:under|below|younger than)\s*(\d{1,3})", t)
    if m:
        return None, int(m.group(1))
    m = re.search(r"(\d{1,3})", t)
    if m:
        return int(m.group(1)), int(m.group(1))
    return None, None


_FEMALE = {"female", "woman", "women", "f", "girl", "girls", "ladies", "lady"}
_MALE = {"male", "man", "men", "m", "boy", "boys", "guys"}


def normalize_gender(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if v in _FEMALE:
        return "female"
    if v in _MALE:
        return "male"
    return None
