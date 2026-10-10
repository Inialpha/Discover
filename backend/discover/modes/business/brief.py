"""Business brief: the structured form of a free-text question. Built by an LLM planner when available,
otherwise by a deterministic heuristic. Age -> bucket mapping is always done in code, never by the LLM."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ...qloo.demographics import age_range_to_buckets, normalize_gender, parse_age_text

MEDIA_KINDS = ["movie", "tv_show", "artist", "podcast"]
DEFAULT_KINDS = ["brand", "movie", "tv_show", "artist", "podcast", "place"]
ALL_KINDS = {"brand", "place", "movie", "tv_show", "artist", "podcast", "book", "game", "destination", "person"}


@dataclass
class Segment:
    label: str
    gender: str | None = None
    age_lo: int | None = None
    age_hi: int | None = None
    age_buckets: list[str] = field(default_factory=list)

    def finalize(self) -> "Segment":
        self.gender = normalize_gender(self.gender)
        if not self.age_buckets and (self.age_lo is not None or self.age_hi is not None):
            self.age_buckets = age_range_to_buckets(self.age_lo, self.age_hi)
        return self


@dataclass
class Brief:
    question: str
    goal: str = "audience"  # audience | media | advertising
    product: str | None = None
    own_brand: str | None = None
    competitors: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    interests: list[dict[str, str]] = field(default_factory=list)  # {"name":..., "kind":...}
    location: str | None = None  # first of `locations` (kept for compatibility)
    locations: list[str] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    domains: list[str] = field(default_factory=lambda: list(DEFAULT_KINDS))
    planner: str = "heuristic"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_LOC = re.compile(r"\b(?:in|around|across|within)\s+([A-Z][\w'’\-]*(?:[ ,]+[A-Z][\w'’\-]*){0,3})")
_MEDIA_WORDS = re.compile(r"\b(media|watch|listen|tv|movies?|films?|music|podcasts?|shows?|streaming|content)\b", re.I)
_CONTENT_WORDS = re.compile(r"\b(content|post|posts|video|videos|reels?|tiktok|instagram|youtube|social media)\b", re.I)
_AD_WORDS = re.compile(r"\b(advertis\w*|campaign|promot\w*|market\w*|ads?|sponsor\w*)\b", re.I)


def heuristic_brief(question: str) -> Brief:
    b = Brief(question=question)
    m = _LOC.search(question)
    if m:
        b.location = re.sub(r"[ ,]+$", "", m.group(1)).strip()
        b.locations = [b.location]
    gender = None
    low = question.lower()
    if re.search(r"\b(women|woman|female|ladies|girls)\b", low):
        gender = "female"
    elif re.search(r"\b(men|man|male|guys|boys)\b", low):
        gender = "male"
    lo, hi = parse_age_text(question) if re.search(r"\d", question) else (None, None)
    if lo is not None and hi is not None and lo == hi and not re.search(r"\b(aged?|years?)\b", low):
        lo = hi = None  # a lone number is probably not an age
    if gender or lo is not None or hi is not None:
        label = " ".join(x for x in [
            {"female": "Women", "male": "Men"}.get(gender or "", "People"),
            f"{lo}-{hi}" if lo is not None and hi is not None else "",
        ] if x)
        b.segments.append(Segment(label, gender, lo, hi).finalize())
    media = bool(_MEDIA_WORDS.search(question))
    ad = bool(_AD_WORDS.search(question))
    content = bool(_CONTENT_WORDS.search(question))
    b.goal = "content" if content else "advertising" if ad else "media" if media else "audience"
    if media and not ad:
        b.domains = list(MEDIA_KINDS)
    elif ad:
        b.domains = ["brand", "place", *MEDIA_KINDS]
    b.notes.append("planned by heuristic (no LLM)")
    return b


def brief_from_llm(question: str, data: dict[str, Any]) -> Brief:
    b = Brief(question=question, planner="llm")
    b.goal = data.get("goal") if data.get("goal") in ("audience", "media", "advertising", "content") else "audience"
    b.product = data.get("product") or None
    b.own_brand = data.get("own_brand") or None
    b.competitors = [str(x) for x in data.get("competitors") or []][:5]
    b.keywords = [str(x) for x in data.get("keywords") or []][:8]
    locs = data.get("locations") if isinstance(data.get("locations"), list) else []
    if not locs and data.get("location"):
        locs = [data["location"]]
    b.locations = [str(x) for x in locs if x][:4]
    b.location = b.locations[0] if b.locations else None
    for it in data.get("interests") or []:
        if isinstance(it, dict) and it.get("name"):
            kind = it.get("kind") if it.get("kind") in ALL_KINDS else "brand"
            b.interests.append({"name": str(it["name"]), "kind": kind})
    for s in data.get("segments") or []:
        if isinstance(s, dict):
            b.segments.append(Segment(
                str(s.get("label") or "Segment"), s.get("gender"),
                s.get("age_min") if isinstance(s.get("age_min"), int) else None,
                s.get("age_max") if isinstance(s.get("age_max"), int) else None,
            ).finalize())
    doms = [d for d in data.get("domains") or [] if d in ALL_KINDS]
    if doms:
        b.domains = doms
    return b


_DEMO_WORDS = {"women", "woman", "men", "man", "male", "female", "girls", "boys", "people", "young", "adults", "youth"}


def _dedupe_interests(b: Brief) -> None:
    seen, out = set(), []
    for it in b.interests:
        key = (it["name"].strip().lower(), it["kind"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    b.interests = out


def clean_keywords(b: Brief) -> Brief:
    """Drop keywords that merely restate demographics/location: they are passed as dedicated signals, and
    resolving them as tags produced junk matches in real runs."""
    _dedupe_interests(b)
    interest_names = {i["name"].strip().lower() for i in b.interests}
    locs = [x.lower() for x in b.locations]
    keep = []
    for k in b.keywords:
        kl = k.strip().lower()
        if kl in interest_names:
            b.notes.append(f"keyword {k!r} dropped (already an interest entity)")
            continue
        if not kl or kl in _DEMO_WORDS or any(kl == l or kl in l for l in locs) or re.fullmatch(r"[\d\s\-–+]+", kl):
            b.notes.append(f"keyword {k!r} dropped (demographic/location is a dedicated signal)")
            continue
        if kl not in [x.lower() for x in keep]:
            keep.append(k)
    b.keywords = keep
    return b


def apply_overrides(b: Brief, *, product=None, own_brand=None, keywords=(), competitors=(), interests=(),
                    locations=(), segments=(), gender=None, age=None, domains=None) -> Brief:
    """CLI flags always win over the planner."""
    if product:
        b.product = product
    if own_brand:
        b.own_brand = own_brand
    b.keywords += [k for k in keywords if k not in b.keywords]
    b.competitors += [k for k in competitors if k not in b.competitors]
    for spec in interests:
        name, _, kind = spec.partition(":")
        b.interests.append({"name": name.strip(), "kind": (kind.strip() or "brand")})
    if locations:
        b.locations = [x for x in locations if x]
    b.location = b.locations[0] if b.locations else None
    if gender or age:
        lo, hi = parse_age_text(age) if age else (None, None)
        label = f"{(normalize_gender(gender) or 'people').title()} {age or ''}".strip()
        b.segments = [Segment(label, gender, lo, hi).finalize()]
    for spec in segments:  # "label:gender:age"
        label, _, rest = spec.partition(":")
        g, _, a = rest.partition(":")
        lo, hi = parse_age_text(a) if a else (None, None)
        b.segments.append(Segment(label.strip(), g or None, lo, hi).finalize())
    if domains:
        b.domains = [d for d in domains if d in ALL_KINDS]
    if not b.segments:
        b.segments.append(Segment("Overall audience"))
    return clean_keywords(b)
