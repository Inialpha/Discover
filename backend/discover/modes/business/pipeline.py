"""Business-mode Qloo pipeline: resolve -> taste -> affinity -> demographics -> heatmap -> compare.

Produces an evidence list (ids E001...) where each item records its source file, which parameter
variant worked, and the normalized data. Failures are evidence too (ok=false) so reports can say what is missing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ...qloo import calls, normalize as nz
from ...qloo.client import CallResult, QlooClient
from .brief import Brief, Segment

ALL_STEPS = ("resolve", "taste", "affinity", "demographics", "heatmap", "compare")


@dataclass
class Evidence:
    items: list[dict[str, Any]] = field(default_factory=list)

    def add(self, step: str, label: str, result: CallResult, data: Any, segment: str | None = None) -> str:
        eid = f"E{len(self.items) + 1:03d}"
        self.items.append({
            "id": eid, "step": step, "label": label, "segment": segment, "ok": result.ok,
            "error": None if result.ok else (result.error or result.skipped_reason),
            "status": result.status, "source_files": result.files,
            "variant_used": result.meta if result.ok else None,
            "synthetic": False, "data": data if result.ok else None,
        })
        return eid


@dataclass
class Resolved:
    entities: list[dict[str, Any]] = field(default_factory=list)  # {"query","kind","entity_id","name","candidates":[...]}
    tags: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def _pick(cands: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    cands = [c for c in cands if c.get("entity_id") or c.get("id")]
    if not cands:
        return None
    exact = [c for c in cands if (c.get("name") or "").lower() == query.lower()]
    return (exact or cands)[0]


_TAG_DENY = ("specialty_dish", "nearby_attraction", ":category:place", "genre:place", "amenit", "payments", "parking", "accessibility")
_TAG_PREFER = {
    "advertising": ("urn:tag:genre:brand", "urn:tag:industry", "urn:tag:interests", "urn:tag:genre:media", "urn:tag:keyword"),
    "media": ("urn:tag:genre:media", "urn:tag:keyword:media", "urn:tag:genre"),
    "audience": ("urn:tag:interests", "urn:tag:genre:media", "urn:tag:genre:brand", "urn:tag:keyword"),
}


def _norm(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def pick_tag(cands: list[dict[str, Any]], query: str, goal: str) -> dict[str, Any] | None:
    """Only accept a tag whose NAME matches the query (Qloo tag search is fuzzy and returns junk such as
    dishes/attractions); among matches prefer tag families relevant to the goal. Otherwise: unresolved."""
    q = _norm(query)
    ok = [c for c in cands if c.get("id") and _norm(c.get("name") or "") == q
          and not any(d in (c.get("id") or "") for d in _TAG_DENY)]
    prefs = _TAG_PREFER.get(goal, _TAG_PREFER["audience"])
    def rank(c):
        cid = c.get("id") or ""
        return next((i for i, p in enumerate(prefs) if cid.startswith(p)), len(prefs))
    return sorted(ok, key=rank)[0] if ok else None


async def resolve(client: QlooClient, brief: Brief, ev: Evidence) -> Resolved:
    out = Resolved()
    wanted: list[tuple[str, str]] = []  # (name, kind)
    if brief.own_brand:
        wanted.append((brief.own_brand, "brand"))
    wanted += [(c, "brand") for c in brief.competitors]
    wanted += [(i["name"], i["kind"]) for i in brief.interests]
    specs = [("ent", n, k, calls.search_entities(f"{k}-{n}", n, k, take=5)) for n, k in wanted]
    specs += [("tag", kw, None, calls.search_tags(f"tag-{kw}", kw, take=10)) for kw in brief.keywords]
    results = await asyncio.gather(*(client.call(s[3]) for s in specs))
    for (kind_, name, k, _), res in zip(specs, results):
        if kind_ == "ent":
            cands = nz.entities_from_search(res.body) if res.ok else []
            top = _pick(cands, name)
            ev.add("resolve", f"entity:{name}", res, {"query": name, "kind": k, "candidates": cands[:5], "chosen": top})
            if top:
                out.entities.append({"query": name, "kind": k, "entity_id": top["entity_id"], "name": top["name"]})
            else:
                out.unresolved.append(name)
        else:
            cands = nz.tags_from_body(res.body) if res.ok else []
            top = pick_tag(cands, name, brief.goal)
            ev.add("resolve", f"tag:{name}", res, {"query": name, "candidates": cands[:5], "chosen": top})
            if top:
                out.tags.append({"query": name, "id": top["id"], "name": top["name"]})
            else:
                out.unresolved.append(name)
    return out


def _signals(seg: Segment, resolved: Resolved, location: str | None, own_only: bool = False) -> calls.Signals:
    return calls.Signals(
        entities=[e["entity_id"] for e in resolved.entities],
        tags=[t["id"] for t in resolved.tags],
        age=list(seg.age_buckets),
        gender=seg.gender,
        location=location,
    )


async def run_pipeline(client: QlooClient, brief: Brief, steps: set[str], take: int = 10) -> tuple[Evidence, Resolved]:
    ev, resolved = Evidence(), Resolved()
    if "resolve" in steps:
        resolved = await resolve(client, brief, ev)
    has_interest = bool(resolved.entities or resolved.tags)
    segments = brief.segments or [Segment("Overall audience")]

    for seg in segments:
        sig = _signals(seg, resolved, brief.location)
        no_signal = sig.is_empty() and not sig.location
        if no_signal:
            ev.items.append({"id": f"E{len(ev.items) + 1:03d}", "step": "plan", "label": "no signals", "segment": seg.label,
                             "ok": False, "error": "no demographic, interest or location signal to query with",
                             "source_files": [], "data": None})
            continue
        tasks: list[tuple[str, str, calls.CallSpec]] = []
        if "taste" in steps:
            tasks.append(("taste", "taste", calls.insights_tags("taste", f"{seg.label}-taste", sig, "urn:tag:genre:media")))
        if "affinity" in steps:
            for kind in brief.domains:
                tasks.append(("affinity", kind, calls.insights_entities(
                    "affinity", f"{seg.label}-{kind}", kind, sig, take=take, allow_no_location=False)))
        if "heatmap" in steps and brief.location and not sig.is_empty():
            tasks.append(("heatmap", "heatmap", calls.insights_heatmap("heatmap", f"{seg.label}-heatmap", sig)))
        results = await asyncio.gather(*(client.call(t[2]) for t in tasks))
        for (step, tag, _), res in zip(tasks, results):
            if step == "taste":
                data = {"tags": nz.tags_from_body(res.body)[:20]} if res.ok else None
            elif step == "affinity":
                data = {"kind": tag, "entities": nz.entities_from_insights(res.body)[:take]} if res.ok else None
            else:
                data = {"points": nz.heatmap_from_body(res.body)[:30]} if res.ok else None
            ev.add(step, f"{seg.label}:{tag}", res, data, seg.label)

    if "demographics" in steps and has_interest:
        sig = calls.Signals(entities=[e["entity_id"] for e in resolved.entities],
                            tags=[t["id"] for t in resolved.tags], location=brief.location)
        res = await client.call(calls.insights_demographics("demographics", "audience-demographics", sig))
        ev.add("demographics", "interest-audience", res, nz.demographics_from_body(res.body) if res.ok else None)

    if "compare" in steps and brief.own_brand and brief.competitors:
        own = [e["entity_id"] for e in resolved.entities if e["query"] == brief.own_brand]
        comp = [e["entity_id"] for e in resolved.entities if e["query"] in brief.competitors]
        if own and comp:
            res = await client.call(calls.compare("compare", "own-vs-competitors", own, comp))
            ev.add("compare", "own-vs-competitors", res, nz.compare_from_body(res.body) if res.ok else None)
    return ev, resolved
