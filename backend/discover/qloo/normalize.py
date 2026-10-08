"""Tolerant normalizers: raw Qloo JSON -> small, stable dicts used by the workflow.

Shapes are based on the real samples in entity_examples/. Anything unknown is skipped rather than
raising, and `shape_of` lets the run summary show what the API actually returned.
"""

from __future__ import annotations

from typing import Any

PROP_WHITELIST = (
    "description", "short_description", "audience_identity", "price_level", "year", "release_year", "release_date", "genre", "genres",
    "publication_year", "address", "geocode", "price_level", "cuisines", "languages", "country", "website",
    "industry", "founded", "headquartered_in", "release_country", "key_markets", "headquartered", "content_rating", "duration", "network", "streaming_platforms",
)


def shape_of(obj: Any, depth: int = 3) -> Any:
    """A compact structural fingerprint (keys / list element shape) for debugging."""
    if depth <= 0:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {k: shape_of(v, depth - 1) for k, v in list(obj.items())[:25]}
    if isinstance(obj, list):
        return [shape_of(obj[0], depth - 1), f"... len={len(obj)}"] if obj else []
    return type(obj).__name__


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _compact_props(props: Any) -> dict[str, Any]:
    if not isinstance(props, dict):
        return {}
    out: dict[str, Any] = {}
    for k in PROP_WHITELIST:
        v = props.get(k)
        if v in (None, "", [], {}):
            continue
        if isinstance(v, str) and len(v) > 280:
            v = v[:277] + "..."
        out[k] = v
    return out


def _external_highlights(ext: Any) -> dict[str, Any]:
    """Pull a few numeric/rating style metrics from external{provider:[...]} or {provider:{...}}."""
    out: dict[str, Any] = {}
    if not isinstance(ext, dict):
        return out
    for provider, val in ext.items():
        items = val if isinstance(val, list) else [val]
        for item in items[:1]:
            if not isinstance(item, dict):
                continue
            picked = {k: v for k, v in item.items() if isinstance(v, (int, float, str)) and k in (
                "rating", "user_rating_count", "review_count", "popularity", "price_level", "followers", "id")}
            if picked:
                out[str(provider)] = picked
    return out


def _tags(raw: Any, limit: int = 8) -> list[dict[str, Any]]:
    out = []
    for t in raw or []:
        if not isinstance(t, dict):
            continue
        out.append({
            "id": t.get("id") or t.get("tag_id"),
            "name": t.get("name"),
            "type": t.get("type"),
            "weight": t.get("weight", t.get("value")),
        })
        if len(out) >= limit:
            break
    return out


def _results(body: Any) -> Any:
    if isinstance(body, dict):
        return body.get("results", body)
    return body


def entities_from_insights(body: Any) -> list[dict[str, Any]]:
    res = _results(body)
    items = res.get("entities") if isinstance(res, dict) else res
    out = []
    for e in items or []:
        if not isinstance(e, dict):
            continue
        q = e.get("query") or {}
        out.append({
            "entity_id": e.get("entity_id") or e.get("id"),
            "name": e.get("name"),
            "type": e.get("type"),
            "subtype": e.get("subtype"),
            "popularity": _num(e.get("popularity")),
            "disambiguation": e.get("disambiguation") or None,
            "location": e.get("location") if isinstance(e.get("location"), dict) else None,
            "affinity": _num(q.get("affinity")) if isinstance(q, dict) else None,
            "measurements": q.get("measurements") if isinstance(q, dict) else None,
            "explainability": q.get("explainability") if isinstance(q, dict) else None,
            "tags": _tags(e.get("tags")),
            "properties": _compact_props(e.get("properties")),
            "external": _external_highlights(e.get("external") or (e.get("properties") or {}).get("external")),
        })
    return out


def entities_from_search(body: Any) -> list[dict[str, Any]]:
    res = _results(body)
    if isinstance(res, dict):
        res = res.get("entities", [])
    out = []
    for e in res or []:
        if not isinstance(e, dict):
            continue
        types = e.get("types") or ([e.get("type")] if e.get("type") else [])
        out.append({
            "entity_id": e.get("entity_id") or e.get("id"),
            "name": e.get("name"),
            "types": types,
            "popularity": _num(e.get("popularity")),
            "disambiguation": e.get("disambiguation"),
            "tags": _tags(e.get("tags"), 5),
        })
    return out


def tags_from_body(body: Any) -> list[dict[str, Any]]:
    res = _results(body)
    items = res.get("tags") if isinstance(res, dict) else res
    out = []
    for t in items or []:
        if not isinstance(t, dict):
            continue
        q = t.get("query") if isinstance(t.get("query"), dict) else {}
        out.append({
            "id": t.get("id") or t.get("tag_id") or t.get("entity_id"),
            "name": t.get("name"),
            "type": t.get("type") or t.get("subtype"),
            "affinity": _num(q.get("affinity")),
            "weight": t.get("weight", t.get("value")),
        })
    return out


def demographics_from_body(body: Any) -> dict[str, Any]:
    """Returns {"raw_keys": [...], "groups": {age|gender|...: {bucket: value}}} tolerant of a few shapes."""
    res = _results(body)
    out: dict[str, Any] = {"groups": {}}
    if isinstance(res, dict):
        ds = res.get("demographics")
        items = ds if isinstance(ds, list) else [res] if ds is None else [ds]
        for d in items:
            if not isinstance(d, dict):
                continue
            # shape A: {"entity_id":..., "query":{"age":{...},"gender":{...}}}
            q = d.get("query") if isinstance(d.get("query"), dict) else d
            for key, val in q.items():
                if isinstance(val, dict) and val and all(_num(v) is not None for v in val.values()):
                    out["groups"].setdefault(key, {}).update({k: _num(v) for k, v in val.items()})
    return out


def heatmap_from_body(body: Any) -> list[dict[str, Any]]:
    res = _results(body)
    items = res.get("heatmap") if isinstance(res, dict) else res
    out = []
    for h in items or []:
        if not isinstance(h, dict):
            continue
        loc = h.get("location") if isinstance(h.get("location"), dict) else h
        q = h.get("query") if isinstance(h.get("query"), dict) else {}
        out.append({
            "geohash": loc.get("geohash") or h.get("geohash"),
            "lat": _num(loc.get("latitude", loc.get("lat"))),
            "lon": _num(loc.get("longitude", loc.get("lon", loc.get("lng")))),
            "name": loc.get("name") or h.get("name"),
            "affinity": _num(q.get("affinity", h.get("affinity"))),
            "affinity_rank": _num(q.get("affinity_rank")),
            "demographics_affinity": _num(q.get("demographics_affinity")),
            "tag_affinity": _num(q.get("tag_affinity")),
            "popularity": _num(q.get("popularity", h.get("popularity"))),
        })
    return out


def compare_from_body(body: Any) -> dict[str, Any]:
    """Real shape: results.tags[{tag_id,name,type,subtype,query{score,a.signal...,b.signal...}}]."""
    res = _results(body)
    if not isinstance(res, dict):
        return {}
    out: dict[str, Any] = {"tags": [], "entities": []}
    for key in ("tags", "entities"):
        for t in res.get(key) or []:
            if not isinstance(t, dict):
                continue
            q = t.get("query") if isinstance(t.get("query"), dict) else {}
            out[key].append({"id": t.get("tag_id") or t.get("entity_id"), "name": t.get("name"),
                             "subtype": t.get("subtype"), "score": _num(q.get("score")),
                             "popularity": _num(t.get("popularity"))})
    return out
