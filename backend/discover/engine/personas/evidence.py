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
from . import culture
from .lean import MARKET
from .intake import ProductIntake
from .scoring import SegmentScore
from .segments import by_id

DEFAULT_KINDS = ("brand", "artist", "tv_show", "place")

# Real run: Qloo names "Tecno" -> "TECNO Mobile" and "Infinix" -> "Infinix Mobile", so an exact-name rule found nothing.
# A hit is accepted if the query's words are the START of its name and any extra words are harmless corporate suffixes.
_SUFFIX_OK = {"mobile", "mobiles", "nigeria", "official", "inc", "ltd", "limited", "group", "company", "co", "corp",
              "corporation", "global", "international", "africa", "phones", "electronics", "technology", "technologies"}


def _words(t: str) -> list[str]:
    import re
    return [w for w in re.split(r"[^a-z0-9]+", (t or "").lower()) if w]


def pick_anchor(cands: list[dict[str, Any]], query: str) -> tuple[dict[str, Any] | None, str | None]:
    """(candidate, how) with how in {'exact','prefix'}; (None, None) when nothing safe matches. Never the first fuzzy hit."""
    exact = _pick(cands, query)
    if exact:
        return exact, "exact"
    q = _words(query)
    for c in cands:
        n = _words(c.get("name") or "")
        if (c.get("entity_id") or c.get("id")) and q and n[: len(q)] == q and set(n[len(q):]) <= _SUFFIX_OK:
            return c, "prefix"
    return None, None


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


async def resolve_and_skew(client: QlooClient, intake: ProductIntake, llm: Any = None, discover: bool = False,
                           want: int = 5, preset: dict[str, Any] | None = None,
                           known_categories: list[dict[str, Any]] | None = None, lean: bool = False) -> dict[str, Any]:
    """Steps 1-2: find competitor anchors (given, and with discover=True also found through Qloo), run the category ladder for
    alternatives and the wider sector, then ask for the audience skew of the competitors (and, separately, of the alternatives)."""
    from .competitors import discover_competitors
    from .ladder import run_ladder
    from .lean import discover_lean
    ev = Evidence()
    finder = discover_lean if lean else discover_competitors
    found = preset if preset is not None else await finder(client, intake, ev, pick_anchor, llm=llm, want=want, discover=discover)
    anchors, unresolved, notes = list(found["anchors"]), found["unresolved"], list(found["notes"])
    market: dict[str, Any] | None = None
    n_direct0 = sum(1 for a in anchors if a.get("tier", "direct") == "direct")
    if discover and llm is not None and (not lean or n_direct0 < 2):  # lean: the market map only when direct competitors are missing
        lad = await run_ladder(client, intake, ev, llm, anchors, known=known_categories)
        notes += lad["notes"]
        have = {a["entity_id"] for a in anchors}
        for b in lad["kept"]:
            n_direct = sum(1 for a in anchors if a.get("tier", "direct") == "direct")
            # direct brands join the competitors; with fewer than 2 direct ones, other tiers stand in so the audience can still be read
            if b["entity_id"] not in have and ((b["tier"] == "direct" and n_direct < want) or n_direct < 2):
                have.add(b["entity_id"])
                anchors.append({"query": b["label"], "entity_id": b["entity_id"], "name": b["name"], "matched_by": "category",
                                "source": "ladder", "tags": b["tags"], "tier": b["tier"], "label": b["label"],
                                "category": b["category"], "scope": b["scope"]})
        market = _market_view(lad, anchors)
    direct = [a for a in anchors if a.get("tier", "direct") == "direct"]
    base = direct if len(direct) >= 2 else anchors  # with too few direct competitors, the others stand in so personas still have data
    age_index: dict[str, float] = {}
    gender_index: dict[str, float] = {}
    if base:
        sig = calls.Signals(entities=[a["entity_id"] for a in base], location=intake.location)
        res = await client.call(calls.insights_demographics("demographics", "anchor-audience-skew", sig))
        data = nz.demographics_from_body(res.body) if res.ok else None
        ev.add("demographics", "anchor audience (competitors): relative index, location-independent", res, data)
        if data:
            age_index = dict((data.get("groups") or {}).get("age", {}))
            gender_index = dict((data.get("groups") or {}).get("gender", {}))
    if market and market["tiers"]["alternative"] and len(direct) >= 2:
        alts = [b["name"] for lab in market["tiers"]["alternative"] for b in lab["brands"]]
        ids = [b["entity_id"] for b in lad["kept"] if b["tier"] == "alternative"][:5]
        if ids:
            res = await client.call(calls.insights_demographics("demographics", "alternatives-audience-skew",
                                                                calls.Signals(entities=ids, location=intake.location)))
            data = nz.demographics_from_body(res.body) if res.ok else None
            eid = ev.add("demographics", "audience of the alternatives: relative index, location-independent", res, data)
            if data:
                market["alternatives_audience"] = {"brands": alts[:5], "age_index": dict((data.get("groups") or {}).get("age", {})),
                                                   "gender_index": dict((data.get("groups") or {}).get("gender", {})), "evidence": eid}
    return {"ev": ev, "anchors": anchors, "unresolved": unresolved, "age_index": age_index, "gender_index": gender_index,
            "notes": notes, "category": found.get("category"), "profiles": found.get("profiles", {}), "market": market,
            "learned": (lad["learned"] if market else [])}


def _market_view(lad: dict[str, Any], anchors: list[dict[str, Any]]) -> dict[str, Any]:
    """What the report shows about the market around the product: tiers with confirmed brands, the need, and what was not confirmed."""
    tiers: dict[str, list[dict[str, Any]]] = {"direct": [], "alternative": [], "sector": []}
    direct_names = [a["name"] for a in anchors if a.get("tier", "direct") == "direct" and a.get("source") != "ladder"]
    if direct_names:
        tiers["direct"].append({"label": "your competitors", "brands": [{"name": n} for n in direct_names]})
    for lab in dict.fromkeys(b["label"] for b in lad["kept"]):
        brands = [b for b in lad["kept"] if b["label"] == lab]
        tiers[brands[0]["tier"]].append({"label": lab, "brands": [{"name": b["name"], "entity_id": b["entity_id"]} for b in brands],
                                         "evidence": [b["evidence"] for b in brands][:1]})
    return {"need": lad["need"], "confirmed": lad["confirmed"] or bool(direct_names), "tiers": tiers,
            "ledger": lad["ledger"], "alternatives_audience": None}


ANCHORED_KINDS = ("brand", "artist", "tv_show")
ANCHORS_PER_CALL = 6


def anchor_ids(anchors: list[dict[str, Any]] | None, limit: int = ANCHORS_PER_CALL) -> list[str]:
    """Entity ids of the competitors to use as taste signals: direct competitors first, then the others that stand in."""
    rows = [a for a in anchors or [] if a.get("entity_id")]
    direct = [a for a in rows if a.get("tier", "direct") == "direct"]
    return [a["entity_id"] for a in (direct if len(direct) >= 2 else rows)][:limit]


async def gather_segments(client: QlooClient, intake: ProductIntake, segments: list[SegmentScore], ev: Evidence,
                          kinds: tuple[str, ...] | list[str] = DEFAULT_KINDS, take: int = 8,
                          anchors: list[dict[str, Any]] | None = None,
                          anchored_kinds: tuple[str, ...] | list[str] = ANCHORED_KINDS) -> None:
    """Step 3: per ranked segment, taste/place lists and a heatmap (age + location signals, no anchors).

    With anchors, a second set of calls per segment adds the competitors as interest signals next to the segment's age and
    location. Those results answer "what do people like this segment, around this product, like", so they are more on
    topic than the demographics-only lists. They feed the culture digest and the name checks only; the plain lists stay
    as they were because interest signals can drown the age signal."""
    tasks: list[tuple[SegmentScore, str, bool, calls.CallSpec]] = []
    ids = anchor_ids(anchors)
    for s in segments:
        sig = calls.Signals(age=list(s.ages), gender=s.gender, location=intake.location)
        for kind in kinds:
            tasks.append((s, kind, False, calls.insights_entities("affinity", f"{s.label}-{kind}", kind, sig, take=take,
                                                                  explain=False, allow_no_location=False)))
        tasks.append((s, "heatmap", False, calls.insights_heatmap("heatmap", f"{s.label}-heatmap", sig)))
        if ids:
            asig = calls.Signals(entities=ids, age=list(s.ages), gender=s.gender, location=intake.location)
            for kind in anchored_kinds:
                tasks.append((s, kind, True, calls.insights_entities("affinity", f"{s.label}-{kind}-anchored", kind, asig, take=take,
                                                                     explain=False, allow_no_location=False)))
    results = await asyncio.gather(*(client.call(t[3]) for t in tasks))
    for (s, kind, anchored, _), res in zip(tasks, results):
        if kind == "heatmap":
            data = {"points": nz.heatmap_from_body(res.body)[:30]} if res.ok else None
            ev.add("heatmap", f"{s.label}:heatmap", res, data, s.label)
        elif anchored:
            data = {"kind": kind, "anchored": True, "entities": nz.entities_from_insights(res.body)[:take]} if res.ok else None
            ev.add("affinity", f"{s.label}:{kind}+competitors", res, data, s.label)
        else:
            data = {"kind": kind, "entities": nz.entities_from_insights(res.body)[:take]} if res.ok else None
            ev.add("affinity", f"{s.label}:{kind}", res, data, s.label)
    _annotate_heatmaps(ev)


MARKET_KINDS = ("tv_show", "artist", "place")
SEGMENT_KINDS = ("tv_show", "artist", "brand")  # tastes that differ by age, asked for each segment. Places do not: live run, Qloo returned the
# same eight New York places in the same order for every age group, so places stay one shared call


async def gather_market(client: QlooClient, intake: ProductIntake, segments: list[SegmentScore], ev: Evidence,
                        anchors: list[dict[str, Any]] | None, take: int = 10, top_segments: int = 6,
                        kinds: tuple[str, ...] | list[str] = MARKET_KINDS,
                        segment_kinds: tuple[str, ...] | list[str] = SEGMENT_KINDS, segment_heatmap: bool = False) -> None:  # live run: no per-segment map had a named area, so it is off
    """Lean step 3. Calls: shows and artists around the competitors (competitors + location), places (location), one heatmap
    (competitors + location), then TV shows, artists and brands for each segment with that segment's age and gender. About 4 + 3 per
    segment calls in all; the per-segment calls are what make the personas different from one another.

    Competitor signals and age signals are never mixed in one call, so neither can drown the other."""
    ids = anchor_ids(anchors)
    loc = intake.location
    tasks: list[tuple[str, str, calls.CallSpec]] = []
    for kind in kinds:
        if kind == "place":
            sig = calls.Signals(location=loc)
        elif ids:
            sig = calls.Signals(entities=ids, location=loc)
        else:
            continue
        tasks.append((MARKET, kind, calls.insights_entities("affinity", f"market-{kind}", kind, sig, take=take, explain=False,
                                                            allow_no_location=False)))
    if ids:
        tasks.append((MARKET, "heatmap", calls.insights_heatmap("heatmap", "market-heatmap", calls.Signals(entities=ids, location=loc))))
    else:
        tasks.append((MARKET, "heatmap", calls.insights_heatmap("heatmap", "market-heatmap", calls.Signals(location=loc))))
    for s in segments[:top_segments]:
        sig = calls.Signals(age=list(s.ages), gender=s.gender, location=loc)
        for kind in segment_kinds:
            tasks.append((s.label, kind, calls.insights_entities("affinity", f"{s.label}-{kind}", kind, sig, take=take, explain=False,
                                                                 allow_no_location=False)))
        if segment_heatmap:  # the areas of the city this age group and gender concentrate in
            tasks.append((s.label, "heatmap", calls.insights_heatmap("heatmap", f"{s.label}-heatmap", sig)))
    results = await asyncio.gather(*(client.call(t[2]) for t in tasks))
    for (label, kind, _), res in zip(tasks, results):
        if kind == "heatmap":
            data = {"points": nz.heatmap_from_body(res.body)[:30]} if res.ok else None
            ev.add("heatmap", f"{label}:heatmap", res, data, label)
        else:
            data = {"kind": kind, "entities": nz.entities_from_insights(res.body)[:take]} if res.ok else None
            ev.add("affinity", f"{label}:{kind}", res, data, label)
    _annotate_heatmaps(ev)


def _mine(it: dict[str, Any], label: str) -> bool:
    """An evidence item belongs to a segment if it is its own or describes the whole market (shared by every segment)."""
    return it.get("segment") in (label, MARKET)


def segment_entities(ev_items: list[dict[str, Any]], seg_label: str) -> list[dict[str, Any]]:
    """Every entity Qloo returned for a segment, each tagged with the evidence id of the call it came from."""
    out: list[dict[str, Any]] = []
    for it in ev_items:
        if it.get("segment") == seg_label and it.get("ok") and it["step"] == "affinity":
            for e in (it.get("data") or {}).get("entities", []):
                out.append({**e, "evidence_id": it["id"]})
    return out


def culture_for(ev_items: list[dict[str, Any]], seg_label: str, other_labels: list[str]) -> dict[str, Any]:
    """Culture digests for one segment (see personas/culture.py):
      market   the audience of the product's competitors and similar brands (same for every segment; empty in the full mode)
      around   the shows, artists and places around those brands (same for every segment)
      segment  who the brands this age group likes are for (their audience text), against the other segments' brands
      taste    the same for this segment's own shows and artists
      platforms  social platforms of all the entities behind both"""
    shared = segment_entities(ev_items, MARKET)
    own = segment_entities(ev_items, seg_label)
    base = [e for lab in other_labels if lab not in (seg_label, MARKET) for e in segment_entities(ev_items, lab)]
    profiled = [{"name": it["data"]["name"], "subtype": "urn:entity:brand", "evidence_id": it["id"],
                 "properties": {"customer_segments": it["data"]["segments"]}}
                for it in ev_items if it["step"] == "brand_profile" and it.get("ok") and (it.get("data") or {}).get("segments")
                and not it["data"].get("rejected")]  # Qloo's own record of each competitor that passed the identity check
    brands = profiled + [e for e in shared if culture._kind(e) == "brand"]
    around = [e for e in shared if culture._kind(e) != "brand"]
    own_brands = [e for e in own if culture._kind(e) == "brand"]
    own_taste = [e for e in own if culture._kind(e) != "brand"]
    base_brands = [e for e in base if culture._kind(e) == "brand"]
    base_taste = [e for e in base if culture._kind(e) != "brand"]
    return {"market": culture.digest(brands, [], top=5, sentences=4, min_support=1 if len(brands) <= 4 else culture.MIN_SUPPORT) if brands else None,
            "around": culture.digest(around, [], top=4, sentences=2) if around else None,
            "segment": culture.digest(own_brands, base_brands, top=5, sentences=3) if own_brands else None,
            "taste": culture.digest(own_taste, base_taste, top=5, sentences=3) if own_taste else None,
            "platforms": culture.platforms(shared + own)}


def segment_view(ev_items: list[dict[str, Any]], seg: SegmentScore, per_kind: int = 5, areas: int = 4) -> dict[str, Any]:
    """Compact per-segment evidence for the persona writer: ids stay attached so claims can cite them."""
    view: dict[str, Any] = {"segment_id": seg.id, "label": seg.label, "ages": list(seg.ages), "lists": {}, "areas": []}
    shared = [i for i in ev_items if i.get("segment") == MARKET]
    for it in shared + [i for i in ev_items if i.get("segment") == seg.label]:  # the segment's own lists override the shared ones
        if not it.get("ok"):
            view.setdefault("missing", []).append({"id": it["id"], "label": it.get("label"), "error": it.get("error")})
            continue
        d = it.get("data") or {}
        if it["step"] == "affinity" and d.get("anchored"):
            continue  # feeds the culture digest and name checks only
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
        if _mine(it, seg_label) and it.get("ok") and it["step"] == "affinity":
            d = it.get("data") or {}
            if d.get("kind") == "place":
                names |= {e.get("name") for e in d.get("entities", []) if e.get("name")}
        if _mine(it, seg_label) and it.get("ok") and it["step"] == "heatmap":
            for p in (it.get("data") or {}).get("points", []):
                names |= {n["name"] for n in p.get("nearby_places", [])}
    return names


def entity_names(ev_items: list[dict[str, Any]], seg_label: str) -> dict[str, str]:
    """name -> evidence id for every entity Qloo returned for the segment (validates 'tastes' claims)."""
    out: dict[str, str] = {}
    for it in ev_items:
        if _mine(it, seg_label) and it.get("ok") and it["step"] == "affinity":
            for e in (it.get("data") or {}).get("entities", []):
                if e.get("name"):
                    out[e["name"]] = it["id"]
    return out


def segment_ages(seg_id: str) -> tuple[str, ...]:
    s = by_id(seg_id)
    return s.ages if s else ()


def place_affinity(ev_items: list[dict[str, Any]], seg_label: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for it in ev_items:
        if _mine(it, seg_label) and it.get("ok") and it["step"] == "affinity" and (it.get("data") or {}).get("kind") == "place":
            for e in it["data"].get("entities", []):
                if e.get("name") and isinstance(e.get("affinity"), (int, float)):
                    out[e["name"]] = float(e["affinity"])
    return out


def shared_evidence_notes(ev_items: list[dict[str, Any]], ranked: list[Any], location: str) -> list[str]:
    """Honest limits computed from the data: segments with identical age bands get identical Qloo lists, and place lists
    for different age groups often overlap heavily (real run: University of Lagos and the same hotels for every group)."""
    notes: list[str] = []
    groups: dict[tuple[str, ...], list[str]] = {}
    for s in ranked:
        groups.setdefault(tuple(s.ages), []).append(s.label)
    for ages, labels in groups.items():
        if len(labels) > 1:
            notes.append(f"{' and '.join(labels)} use the same age bands ({', '.join(ages)}), so Qloo returned identical lists "
                         "for them; they differ only by their rule-based description, not by Qloo data.")
    sets = [set(place_names(ev_items, s.label)) for s in ranked]
    sets = [x for x in sets if x]
    if len(sets) >= 2:
        pairs = [len(a & b) / len(a | b) for i, a in enumerate(sets) for b in sets[i + 1:]]
        avg = sum(pairs) / len(pairs)
        if avg >= 0.7:
            notes.append(f"Qloo's place results for the different age groups in {location} overlap by {avg:.0%} on average "
                         "(Jaccard), so 'where to reach them' says more about the city than about the age group.")
    return notes
