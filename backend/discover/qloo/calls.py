"""Builders for Qloo calls.

Parameter spellings that are not verified against the live API are expressed as ordered variants
(see client.QlooClient). The variant that worked is recorded in each call's meta.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import CallSpec, Variant

ENTITY_KINDS = ("brand", "place", "movie", "tv_show", "artist", "podcast", "book", "game", "destination", "person")


# "auto" = per-call default order with fallback; "signal"/"filter" force one spelling; "both" sends both.
LOCATION_MODE = "auto"


def set_location_mode(mode: str) -> None:
    global LOCATION_MODE
    if mode not in ("auto", "signal", "filter", "both"):
        raise ValueError(mode)
    LOCATION_MODE = mode


def entity_urn(kind: str) -> str:
    return kind if kind.startswith("urn:") else f"urn:entity:{kind}"


@dataclass
class Signals:
    entities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    audiences: list[str] = field(default_factory=list)
    age: list[str] = field(default_factory=list)
    gender: str | None = None
    location: str | None = None  # a place name (Qloo resolves it)

    def demographic_params(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if self.audiences:
            p["signal.demographics.audiences"] = ",".join(self.audiences)
        if self.age:
            p["signal.demographics.age"] = ",".join(self.age)
        if self.gender:
            p["signal.demographics.gender"] = self.gender
        return p

    def interest_params(self) -> dict[str, str]:
        p: dict[str, str] = {}
        if self.entities:
            p["signal.interests.entities"] = ",".join(self.entities)
        if self.tags:
            p["signal.interests.tags"] = ",".join(self.tags)
        return p

    def is_empty(self) -> bool:
        return not (self.entities or self.tags or self.audiences or self.age or self.gender)


def search_entities(label: str, query: str, kind: str | None = None, take: int = 5, step: str = "resolve") -> CallSpec:
    base = {"query": query, "take": str(take)}
    variants: list[Variant] = []
    if kind:
        variants.append(Variant({**base, "types": entity_urn(kind)}, {"type_param": "types"}))
        variants.append(Variant({**base, "filter.type": entity_urn(kind)}, {"type_param": "filter.type"}))
    variants.append(Variant(dict(base), {"type_param": None}))
    return CallSpec(step, label, "/search", variants, note=f"entity search: {query!r} kind={kind}")


def search_tags(label: str, query: str, take: int = 5, step: str = "resolve") -> CallSpec:
    take_s = str(take)
    return CallSpec(
        step,
        label,
        "/v2/tags",
        [
            Variant({"filter.query": query, "take": take_s}, {"query_param": "filter.query"}),
            Variant({"query": query, "take": take_s}, {"query_param": "query"}),
        ],
        note=f"tag search: {query!r}",
    )


def _location_variants(
    base: dict[str, str], location: str | None, order: tuple[str, ...], meta: dict, allow_none: bool = False
) -> list[Variant]:
    if not location:
        return [Variant(dict(base), {**meta, "location_param": None})]
    if LOCATION_MODE == "both":
        return [Variant({**base, "signal.location.query": location, "filter.location.query": location},
                        {**meta, "location_param": "both"})]
    if LOCATION_MODE in ("signal", "filter"):
        order = (LOCATION_MODE,)
    out = [Variant({**base, f"{k}.location.query": location}, {**meta, "location_param": f"{k}.location.query"}) for k in order]
    if allow_none:
        out.append(Variant(dict(base), {**meta, "location_param": None, "location_dropped": True}))
    return out


def insights_entities(
    step: str,
    label: str,
    kind: str,
    signals: Signals,
    take: int = 10,
    explain: bool = True,
    allow_no_location: bool = False,
) -> CallSpec:
    base = {"filter.type": entity_urn(kind), "take": str(take), **signals.interest_params(), **signals.demographic_params()}
    if explain and (signals.entities or signals.tags):
        base["feature.explainability"] = "true"
    order = ("signal", "filter") if kind != "place" else ("filter", "signal")
    variants = _location_variants(base, signals.location, order, {"kind": kind}, allow_none=allow_no_location)
    return CallSpec(step, label, "/v2/insights", variants, note=f"entity insights kind={kind}")


def insights_tags(step: str, label: str, signals: Signals, tag_type: str | None = None, take: int = 15) -> CallSpec:
    base = {"filter.type": "urn:tag", "take": str(take), **signals.interest_params(), **signals.demographic_params()}
    meta = {"tag_type": tag_type}
    variants: list[Variant] = []
    for loc in _location_variants(base, signals.location, ("signal", "filter"), meta, allow_none=True):
        if tag_type:
            variants.append(Variant({**loc.params, "filter.tag.types": tag_type}, {**loc.meta, "tag_type_param": "filter.tag.types"}))
        variants.append(loc)
    # de-duplicate identical param sets while keeping order
    seen, uniq = set(), []
    for v in variants:
        key = tuple(sorted(v.params.items()))
        if key not in seen:
            seen.add(key)
            uniq.append(v)
    return CallSpec(step, label, "/v2/insights", uniq, note="taste (tag) insights")


def insights_demographics(step: str, label: str, signals: Signals) -> CallSpec:
    base = {"filter.type": "urn:demographics", **signals.interest_params()}
    # Demographic *signals* would be circular here; only interests/location condition the output.
    variants = _location_variants(base, signals.location, ("signal", "filter"), {}, allow_none=True)
    return CallSpec(step, label, "/v2/insights", variants, note="who is this audience (demographics)")


def insights_heatmap(step: str, label: str, signals: Signals, take: int | None = None) -> CallSpec:
    base = {"filter.type": "urn:heatmap", **signals.interest_params(), **signals.demographic_params()}
    if take:
        base["take"] = str(take)
    variants = _location_variants(base, signals.location, ("filter", "signal"), {})
    return CallSpec(step, label, "/v2/insights", variants, note="heatmap")


def compare(step: str, label: str, a: list[str], b: list[str], kind: str | None = None) -> CallSpec:
    base: dict[str, str] = {}
    if kind:
        base["filter.type"] = entity_urn(kind)
    va = {**base, "a.signal.interests.entities": ",".join(a), "b.signal.interests.entities": ",".join(b)}
    vb = {**base, "signal.interests.entities.a": ",".join(a), "signal.interests.entities.b": ",".join(b)}
    return CallSpec(
        step,
        label,
        "/v2/analysis/compare",
        [Variant(va, {"spelling": "a./b. prefix"}), Variant(vb, {"spelling": "suffix"})],
        note="compare two entity groups",
    )
