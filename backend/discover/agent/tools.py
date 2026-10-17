"""Qloo tools for the agent. Each tool makes ONE real Qloo call, filters the raw response to what the agent needs, and
records it in a ledger (call ids Q01, Q02, ...). Tool errors come back as observations so the agent can correct itself."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..qloo import calls, normalize as nz
from ..qloo.client import CallSpec, QlooClient, Variant

MAX_OBS_CHARS = 2600
KINDS = calls.ENTITY_KINDS


def short_tag(tid: str) -> str:
    return tid[len("urn:tag:"):] if tid.startswith("urn:tag:") else tid


def full_tag(tid: str) -> str:
    tid = tid.strip()
    return tid if tid.startswith("urn:") else f"urn:tag:{tid}"


def _name_from_id(tid: str) -> str:
    return tid.rsplit(":", 1)[-1].replace("_", " ")


NAMESPACES_OF_INTEREST = ("competitor_brand", "similar_brand", "customer_segment", "industry", "product_service", "price_range")


# Namespaces that tell the agent WHAT a brand is. Aesthetic/lifestyle/core_value tags are noise for this job and cost tokens.
KEEP_NS = ("genre:brand", "brand_type", "brand_subtype", "industry", "product_service", "product_category", "competitor_brand",
           "similar_brand", "customer_segment", "price_range", "business_model", "wikipedia_category")


def group_tags(tags: list[dict[str, Any]], keep_genre: int = 6) -> dict[str, list[str]]:
    """Tag list -> {namespace: [names]} using the namespace in the id (urn:tag:<ns>:...), identity-relevant namespaces only."""
    out: dict[str, list[str]] = {}
    for t in tags or []:
        tid = str(t.get("id") or "")
        parts = short_tag(tid).split(":")
        ns = parts[0] if parts else "?"
        if ns == "genre" and len(parts) > 1:
            ns = f"genre:{parts[1]}"
        if ns not in KEEP_NS:
            continue
        label = (t.get("name") or _name_from_id(tid)) if ns in NAMESPACES_OF_INTEREST else short_tag(tid).split(":", 1)[-1] if ns != "genre:brand" else short_tag(tid)[len("genre:brand:"):] or "brand"
        out.setdefault(ns, [])
        if label not in out[ns] and len(out[ns]) < (keep_genre if ns.startswith("genre") else 6):
            out[ns].append(label)
    return out


@dataclass
class Ledger:
    entries: list[dict[str, Any]] = field(default_factory=list)
    seen_entities: dict[str, dict[str, Any]] = field(default_factory=dict)  # entity_id -> {name, call, kind}
    seen_tags: set[str] = field(default_factory=set)

    def add(self, tool: str, args: dict[str, Any], ok: bool, summary: Any, files: list[str] | None = None, error: str | None = None) -> str:
        cid = f"Q{len(self.entries) + 1:02d}"
        self.entries.append({"id": cid, "tool": tool, "args": args, "ok": ok, "error": error, "files": files or [], "observation": summary})
        return cid

    def ids(self) -> set[str]:
        return {e["id"] for e in self.entries}


class Toolbox:
    def __init__(self, client: QlooClient, location: str):
        self.client, self.location, self.ledger = client, location, Ledger()
        self._absorbed: list[str] = []

    # ------------------------------------------------------------------------------------------ catalogue
    @staticmethod
    def catalogue() -> list[dict[str, Any]]:
        return [
            {"tool": "qloo_help", "args": {"topic": "overview|kinds|filters|signals|weights|demographics|tags|response|pitfalls|recipes"},
             "does": "Reference on Qloo parameters, filters, signals, tag namespaces, response shapes, known pitfalls and step-by-step recipes. Free (no Qloo call). Read it when unsure which parameter to use."},
            {"tool": "search_entity", "args": {"query": "str", "kind": f"one of {list(KINDS)}, default brand"},
             "does": "Find entities by name. Returns id, name, popularity, and tags grouped by namespace. Names can resolve to the wrong entity (a brand name may be a university): read the tags."},
            {"tool": "entity_record", "args": {"entity_id": "str"},
             "does": "Full record: tags grouped by namespace, including competitor_brand, similar_brand, customer_segment, industry, product_service names when Qloo has them."},
            {"tool": "find_tags", "args": {"query": "str", "namespace": "optional, e.g. genre:brand, genre:music, lifestyle:qloo"},
             "does": "Find tag ids by meaning (semantic). Use the returned ids in insights.filter_tags / interest_tags."},
            {"tool": "tag_namespaces", "args": {"kind": "entity kind"}, "does": "List the tag namespaces that exist for an entity kind."},
            {"tool": "insights", "args": {"kind": "entity kind", "filter_tags": "[tag ids] HARD category filter", "filter_operator": "union|intersection",
                                         "interest_entities": "[entity ids] taste signal", "interest_tags": "[tag ids] SOFT taste signal",
                                         "age": "[24_and_younger,25_to_29,30_to_34,35_to_44,45_to_54,55_and_older]", "gender": "male|female",
                                         "weights": "{interests.entities|interests.tags|demographics.age|demographics.audiences: very_low..very_high}",
                                         "exclude_tags": "[tag ids] documented, unverified", "audiences": "[urn:audience:...] documented, unverified",
                                         "use_location": "bool, default true", "take": "int<=15"},
             "does": "Ranked entities. Brands: location is a soft signal only. Combine filter_tags (category) with interest_entities (anchor) to rank category brands by similarity."},
            {"tool": "audience_taste", "args": {"interest_entities": "[ids]", "tag_type": "optional namespace urn", "age": "[..]", "gender": "optional"},
             "does": "Tags (tastes) that the audience of these entities over-indexes on."},
            {"tool": "audience_demographics", "args": {"entity_ids": "[ids]"},
             "does": "Age and gender relative index of the audience of these entities (an index, not a share)."},
            {"tool": "heatmap", "args": {"interest_entities": "[ids]", "age": "[..]"}, "does": "Areas in the location where this audience concentrates (lat/lon, affinity; no names)."},
            {"tool": "compare", "args": {"a": "[entity ids]", "b": "[entity ids]"}, "does": "Tags shared by two groups' audiences (shared territory)."},
        ]

    # ------------------------------------------------------------------------------------------ dispatch
    ALIASES = {"limit": "take", "top": "take", "n": "take", "entity_ids": "entity_id", "id": "entity_id"}
    HARMLESS = {"location", "namespace", "country", "city"}  # models add these; the location is fixed by the run

    def _tidy(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Absorb harmless slips (limit vs take, a stray location) instead of wasting a step; the agent is told what was absorbed."""
        out: dict[str, Any] = {}
        for k, v in args.items():
            if name in ("search_entity", "entity_record", "find_tags", "tag_namespaces", "audience_demographics", "audience_taste", "heatmap", "compare") and k == "use_location":
                self._absorbed.append(k)
                continue
            if k in self.HARMLESS and not (name == "find_tags" and k == "namespace") and not (name == "tag_namespaces"):
                self._absorbed.append(k)
                continue
            k2 = self.ALIASES.get(k, k)
            if k2 == "entity_id" and name == "audience_demographics":
                k2, v = "entity_ids", v if isinstance(v, list) else [v]
            if k2 == "take" and name not in ("insights",):
                self._absorbed.append(k)
                continue
            if k2 == "entity_id" and name not in ("entity_record",) and k2 != k:
                k2 = k
            if k == "use_location" and not isinstance(v, bool):
                v = bool(v) and str(v).lower() not in ("false", "no", "0")
            out[k2] = v
        return out

    async def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = getattr(self, f"t_{name}", None)
        if fn is None or name.startswith("_"):
            cid = self.ledger.add(name, args, False, None, error="unknown tool")
            return {"call": cid, "ok": False, "error": f"unknown tool {name!r}; tools: {[t['tool'] for t in self.catalogue()]}"}
        args = self._tidy(name, dict(args or {}))
        bad = [k for k, v in (args or {}).items() if "{{" in json.dumps(v, default=str)]
        if bad:
            msg = (f"arguments {bad} contain a template ('{{{{...}}}}'). Arguments must be literal values copied from earlier results "
                   "(e.g. the actual entity id or tag id string).")
            return {"call": self.ledger.add(name, args, False, None, error=msg), "ok": False, "error": msg}
        try:
            obs, files, ok, err = await fn(**(args or {}))
        except TypeError as exc:
            import inspect
            allowed = [p for p in inspect.signature(fn).parameters if p != "kw"]
            msg = f"bad arguments: {exc}. Allowed for {name}: {allowed}" + (" plus insights signal arguments" if name == "insights" else "")
            return {"call": self.ledger.add(name, args, False, None, error=msg), "ok": False, "error": msg}
        cid = self.ledger.add(name, args, ok, obs if ok else None, files, err)
        out: dict[str, Any] = {"call": cid, "ok": ok}
        if self._absorbed:
            out["note"] = f"ignored arguments {sorted(set(self._absorbed))} (the location is fixed; use only the listed argument names)"
            self._absorbed = []
        if ok:
            out["result"] = obs
        else:
            out["error"] = err
        return out

    async def _call(self, spec: CallSpec):
        res = await self.client.call(spec)
        files = list(res.files or ([res.file] if res.file else []))
        return res, files

    # ------------------------------------------------------------------------------------------ tools
    def _remember(self, ents: list[dict[str, Any]], kind: str) -> None:
        cid = f"Q{len(self.ledger.entries) + 1:02d}"
        for e in ents:
            if e.get("entity_id"):
                self.ledger.seen_entities[e["entity_id"]] = {"name": e.get("name"), "call": cid, "kind": kind,
                                                             "tags": [str(t.get("id")) for t in e.get("tags") or []]}

    def _ent_view(self, e: dict[str, Any], with_tags: bool = True) -> dict[str, Any]:
        v: dict[str, Any] = {"id": e.get("entity_id"), "name": e.get("name")}
        if isinstance(e.get("popularity"), float):
            v["pop"] = round(e["popularity"], 3)
        if isinstance(e.get("affinity"), float):
            v["aff"] = round(e["affinity"], 2)
        if e.get("disambiguation"):
            v["info"] = str(e["disambiguation"])[:50]
        if with_tags and e.get("tags"):
            g = group_tags(e["tags"])
            v["tags"] = {k: x[:3] for k, x in list(g.items())[:6]}
        return v

    async def t_qloo_help(self, topic: str = "overview"):
        from .reference import help_text
        return {"topic": topic, "text": help_text(topic)}, [], True, None

    async def t_search_entity(self, query: str, kind: str = "brand"):
        res, files = await self._call(calls.search_entities(f"agent-search-{query}", str(query), kind if kind in KINDS else None, take=6, step="agent"))
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        ents = nz.entities_from_search(res.body, tag_limit=40)[:6]
        self._remember(ents, kind)
        return {"entities": [self._ent_view(e) for e in ents]}, files, True, None

    async def t_entity_record(self, entity_id: str):
        res, files = await self._call(calls.entity_by_id(f"agent-record-{entity_id}", str(entity_id), step="agent"))
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        ex = nz.entity_extras(res.body)
        known = self.ledger.seen_entities.get(entity_id, {})
        return {"entity": {"id": entity_id, "name": known.get("name")}, "tags": group_tags(ex.get("tags") or [], keep_genre=6)}, files, True, None

    async def t_find_tags(self, query: str, namespace: str | None = None):
        if namespace:
            ns = namespace if namespace.startswith("urn:") else f"urn:tag:{namespace}"
            spec = calls.tags_of_type(f"agent-tags-{query}", ns, query=str(query), take=12, step="agent", semantic=True)
        else:
            spec = CallSpec("agent", f"agent-tags-{query}", "/v2/tags",
                            [Variant({"filter.query": str(query), "take": "12", "feature.semantic_search": "true"}, {}),
                             Variant({"filter.query": str(query), "take": "12"}, {})], note="tag search")
        res, files = await self._call(spec)
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        tags = nz.tags_from_body(res.body)[:12]
        for t in tags:
            if t.get("id"):
                self.ledger.seen_tags.add(full_tag(str(t["id"])))
        return {"tags": [{"id": short_tag(str(t["id"])), "name": t.get("name")} for t in tags if t.get("id")]}, files, True, None

    async def t_tag_namespaces(self, kind: str = "brand"):
        res, files = await self._call(calls.tag_types(f"agent-ns-{kind}", kind if kind in KINDS else "brand", take=50, step="agent"))
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        return {"namespaces": [short_tag(str(t["id"])) for t in nz.tag_types_from_body(res.body) if t.get("id")][:40]}, files, True, None

    def _signals(self, **kw: Any) -> calls.Signals:
        age = kw.get("age") or []
        ents = [str(x) for x in kw.get("interest_entities") or []]
        tags = [full_tag(str(x)) for x in kw.get("interest_tags") or []]
        loc = self.location if kw.get("use_location", True) else None
        w = {k: v for k, v in (kw.get("weights") or {}).items() if v in ("very_low", "low", "medium", "high", "very_high")}
        return calls.Signals(entities=ents, tags=tags, filter_tags=[full_tag(str(x)) for x in kw.get("filter_tags") or []],
                             filter_operator=kw.get("filter_operator") if kw.get("filter_operator") in ("union", "intersection") else None,
                             exclude_tags=[full_tag(str(x)) for x in kw.get("exclude_tags") or []],
                             audiences=[str(x) for x in kw.get("audiences") or []],
                             age=[str(a) for a in age], gender=kw.get("gender") if kw.get("gender") in ("male", "female") else None,
                             location=loc, weights=w)

    async def t_insights(self, kind: str = "brand", take: int = 10, **kw: Any):
        if kind not in KINDS:
            return None, [], False, f"kind must be one of {list(KINDS)}"
        allowed = {"filter_tags", "filter_operator", "interest_entities", "interest_tags", "age", "gender", "weights", "use_location", "exclude_tags", "audiences"}
        unknown = sorted(set(kw) - allowed)
        if unknown:
            return None, [], False, f"unknown insights arguments {unknown}. Allowed: kind, take, {sorted(allowed)}"
        sig = self._signals(**kw)
        take = max(1, min(int(take), 15))
        spec = calls.insights_entities("agent", f"agent-insights-{kind}", kind, sig, take=take, explain=False, allow_no_location=True)
        res, files = await self._call(spec)
        note = None
        if not res.ok and sig.weights:  # weights are documented but not live-verified: retry without, and say so
            sig.weights = {}
            res, files = await self._call(calls.insights_entities("agent", f"agent-insights-{kind}-noweights", kind, sig, take=take,
                                                                 explain=False, allow_no_location=True))
            note = "weights were rejected by Qloo and were dropped"
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        ents = nz.entities_from_insights(res.body)[:take]
        self._remember(ents, kind)
        out: dict[str, Any] = {"entities": [self._ent_view(e) for e in ents]}
        if note:
            out["note"] = note
        if not ents:
            out["note"] = (note + "; " if note else "") + "no results: the filter may be too narrow for this location, try use_location=false or a broader tag"
        return out, files, True, None

    async def t_audience_taste(self, interest_entities: list[str], tag_type: str | None = None, **kw: Any):
        sig = self._signals(interest_entities=interest_entities, age=kw.get("age"), gender=kw.get("gender"))
        res, files = await self._call(calls.insights_tags("agent", "agent-audience-taste", sig, tag_type=tag_type, take=15))
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        return {"tags": [{"id": short_tag(str(t["id"])), "name": t.get("name"),
                          **({"aff": round(t["affinity"], 2)} if isinstance(t.get("affinity"), float) else {})}
                         for t in nz.tags_from_body(res.body)[:15] if t.get("id")]}, files, True, None

    async def t_audience_demographics(self, entity_ids: list[str]):
        sig = calls.Signals(entities=[str(x) for x in entity_ids], location=self.location)
        res, files = await self._call(calls.insights_demographics("agent", "agent-demographics", sig))
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        g = (nz.demographics_from_body(res.body).get("groups") or {})
        return {"age_index": {k: round(v, 2) for k, v in (g.get("age") or {}).items()},
                "gender_index": {k: round(v, 2) for k, v in (g.get("gender") or {}).items()},
                "note": "relative index, noisy, not a share"}, files, True, None

    async def t_heatmap(self, interest_entities: list[str] | None = None, age: list[str] | None = None):
        sig = self._signals(interest_entities=interest_entities, age=age)
        res, files = await self._call(calls.insights_heatmap("agent", "agent-heatmap", sig, take=10))
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        pts = nz.heatmap_from_body(res.body)[:8]
        return {"areas": [{"lat": p["lat"], "lon": p["lon"], **({"aff": round(p["affinity"], 2)} if isinstance(p.get("affinity"), float) else {})}
                          for p in pts]}, files, True, None

    async def t_compare(self, a: list[str], b: list[str]):
        res, files = await self._call(calls.compare("agent", "agent-compare", [str(x) for x in a], [str(x) for x in b]))
        if not res.ok:
            return None, files, False, res.error or f"HTTP {res.status}"
        d = nz.compare_from_body(res.body)
        return {"shared_tags": [{"id": short_tag(str(t["id"])), "name": t.get("name"), "score": t.get("score")} for t in d.get("tags", [])[:12]]}, files, True, None


def clip(obj: Any, limit: int = MAX_OBS_CHARS) -> Any:
    """Keep an observation small enough for the agent's context. Lists are shortened before text is cut."""
    import json
    s = json.dumps(obj, ensure_ascii=False)
    if len(s) <= limit:
        return obj
    if isinstance(obj, dict):
        o = dict(obj)
        for k, v in list(o.items()):
            if isinstance(v, list) and len(v) > 3:
                o[k] = v[: max(3, len(v) // 2)]
        o["_clipped"] = True
        return clip(o, limit) if len(json.dumps(o, ensure_ascii=False)) < len(s) else {"_clipped": True, "text": s[:limit]}
    return {"_clipped": True, "text": s[:limit]}
