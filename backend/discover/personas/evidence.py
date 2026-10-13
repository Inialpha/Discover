"""Persona step 2: Qloo evidence for the ranked segments.

Calls (all bounded by the client's call budget):
  1. resolve each competitor/anchor brand by exact name (fuzzy first hits are rejected, as in the business pipeline);
  2. ONE demographics call for the resolved anchors: which age bands the competitor audience skews to
     (a relative index, not a share). This is the only input to `qloo_fit`;
  3. per ranked segment, entity insights (brand, artist, tv_show, place by default) and a heatmap, using the
     segment's age bands + the location as signals. Anchors are deliberately NOT sent here, because interest
     signals drown out the age signal and every segment would get the same list.
Heatmap areas are named in code from nearby returned places; nothing is named by the LLM.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..modes.business.pipeline import Evidence, _annotate_heatmaps, _pick
from ..qloo import calls, normalize as nz
from ..qloo.client import QlooClient
from .intake import ProductIntake
from .scoring import SegmentScore
from .segments import by_id

DEFAULT_KINDS = ("brand", "artist", "tv_show", "place")


def index_to_fit(idx: float) -> float:
    """Map a signed Qloo audience index (about -1..+1) to 0..1: 0 index -> 0.5, strong skew -> toward 1, avoidance -> 0."""
    return max(0.0, min(1.0, 0.5 + idx / 2.0))


def qloo_fit_from_age_index(age_index: dict[str, float], segments: list[Any]) -> dict[str, float]:
    # `segments`: anything with .id and .ages (rule Segments or SegmentScores)
    """segment id -> mean fit over the segment's age bands that Qloo returned an index for (none -> no entry)."""
    out: dict[str, float] = {}
    for s in segments:
        vals = [index_to_fit(age_index[b]) for b in s.ages if isinstance(age_index.get(b), (int, float))]
        if vals:
            out[s.id] = round(sum(vals) / len(vals), 4)
    return out


async def resolve_and_skew(client: QlooClient, intake: ProductIntake) -> dict[str, Any]:
    """Steps 1-2: resolve competitor anchors, then ask once for their audience's age/gender skew."""
    ev = Evidence()
    unresolved: list[str] = []
    anchors: list[dict[str, str]] = []
    if intake.competitors:
        specs = [calls.search_entities(f"brand-{n}", n, "brand", take=5) for n in intake.competitors]
        results = await asyncio.gather(*(client.call(s) for s in specs))
        for name, res in zip(intake.competitors, results):
            cands = nz.entities_from_search(res.body) if res.ok else []
            top = _pick(cands, name)
            ev.add("resolve", f"brand:{name}", res, {"query": name, "kind": "brand", "candidates": cands[:5], "chosen": top})
            if top:
                anchors.append({"query": name, "entity_id": top["entity_id"], "name": top["name"]})
            else:
                unresolved.append(name)
    age_index: dict[str, float] = {}
    gender_index: dict[str, float] = {}
    if anchors:
        sig = calls.Signals(entities=[a["entity_id"] for a in anchors], location=intake.location)
        res = await client.call(calls.insights_demographics("demographics", "anchor-audience-skew", sig))
        data = nz.demographics_from_body(res.body) if res.ok else None
        ev.add("demographics", "anchor audience (competitors): relative index, location-independent", res, data)
        if data:
            age_index = dict((data.get("groups") or {}).get("age", {}))
            gender_index = dict((data.get("groups") or {}).get("gender", {}))
    return {"ev": ev, "anchors": anchors, "unresolved": unresolved, "age_index": age_index, "gender_index": gender_index}


async def gather_segments(client: QlooClient, intake: ProductIntake, segments: list[SegmentScore], ev: Evidence,
                          kinds: tuple[str, ...] | list[str] = DEFAULT_KINDS, take: int = 8) -> None:
    """Step 3: per ranked segment, taste/place lists and a heatmap (age + location signals, no anchors)."""
    tasks: list[tuple[SegmentScore, str, calls.CallSpec]] = []
    for s in segments:
        sig = calls.Signals(age=list(s.ages), gender=s.gender, location=intake.location)
        for kind in kinds:
            tasks.append((s, kind, calls.insights_entities("affinity", f"{s.label}-{kind}", kind, sig, take=take,
                                                           explain=False, allow_no_location=False)))
        tasks.append((s, "heatmap", calls.insights_heatmap("heatmap", f"{s.label}-heatmap", sig)))
    results = await asyncio.gather(*(client.call(t[2]) for t in tasks))
    for (s, kind, _), res in zip(tasks, results):
        if kind == "heatmap":
            data = {"points": nz.heatmap_from_body(res.body)[:30]} if res.ok else None
            ev.add("heatmap", f"{s.label}:heatmap", res, data, s.label)
        else:
            data = {"kind": kind, "entities": nz.entities_from_insights(res.body)[:take]} if res.ok else None
            ev.add("affinity", f"{s.label}:{kind}", res, data, s.label)
    _annotate_heatmaps(ev)


def segment_view(ev_items: list[dict[str, Any]], seg: SegmentScore, per_kind: int = 5, areas: int = 4) -> dict[str, Any]:
    """Compact per-segment evidence for the persona writer: ids stay attached so claims can cite them."""
    view: dict[str, Any] = {"segment_id": seg.id, "label": seg.label, "ages": list(seg.ages), "lists": {}, "areas": []}
    for it in ev_items:
        if it.get("segment") != seg.label:
            continue
        if not it.get("ok"):
            view.setdefault("missing", []).append({"id": it["id"], "label": it.get("label"), "error": it.get("error")})
            continue
        d = it.get("data") or {}
        if it["step"] == "affinity":
            view["lists"][d.get("kind")] = {"evidence_id": it["id"], "items": [
                {"name": e.get("name"), **({"affinity": round(e["affinity"], 2)} if isinstance(e.get("affinity"), float) else {}),
                 **({"address": (e.get("properties") or {}).get("address")} if (e.get("properties") or {}).get("address") else {}),
                 **({"info": str(e["disambiguation"])[:60]} if e.get("disambiguation") else {})}
                for e in d.get("entities", [])[:per_kind]]}
        elif it["step"] == "heatmap":
            pts = sorted(d.get("points", []), key=lambda p: -(p.get("affinity") or 0))
            named = [p for p in pts if p.get("nearby_places")][:areas]
            view["areas"] = {"evidence_id": it["id"], "named_by_nearby_place": [
                {"near": p["nearby_places"][0]["name"], "km": p["nearby_places"][0]["km"],
                 **({"affinity": round(p["affinity"], 2)} if isinstance(p.get("affinity"), float) else {})} for p in named],
                "unnamed_areas_in_data": max(0, len(pts) - len(named))}
    return view


def place_names(ev_items: list[dict[str, Any]], seg_label: str) -> set[str]:
    """Names of places Qloo returned for a segment, used to validate any 'where to reach them' claim."""
    names: set[str] = set()
    for it in ev_items:
        if it.get("segment") == seg_label and it.get("ok") and it["step"] == "affinity":
            d = it.get("data") or {}
            if d.get("kind") == "place":
                names |= {e.get("name") for e in d.get("entities", []) if e.get("name")}
        if it.get("segment") == seg_label and it.get("ok") and it["step"] == "heatmap":
            for p in (it.get("data") or {}).get("points", []):
                names |= {n["name"] for n in p.get("nearby_places", [])}
    return names


def entity_names(ev_items: list[dict[str, Any]], seg_label: str) -> dict[str, str]:
    """name -> evidence id for every entity Qloo returned for the segment (validates 'tastes' claims)."""
    out: dict[str, str] = {}
    for it in ev_items:
        if it.get("segment") == seg_label and it.get("ok") and it["step"] == "affinity":
            for e in (it.get("data") or {}).get("entities", []):
                if e.get("name"):
                    out[e["name"]] = it["id"]
    return out


def segment_ages(seg_id: str) -> tuple[str, ...]:
    s = by_id(seg_id)
    return s.ages if s else ()
