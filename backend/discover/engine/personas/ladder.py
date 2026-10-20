"""The category ladder: finds the market around ANY product, with Qloo as the judge and no product-specific code.

A product's competition is not only brands that sell the same thing. It is whatever else solves the customer's problem
(a petrol generator for a solar panel) and the wider industry. The ladder looks for all three, in tiers:

  direct       same kind of product
  alternative  a different product that solves the same problem
  sector       the wider industry

How it works (LLM calls kept low: one to map the market, one batched fit check per round, at most MAX_ROUNDS rounds):
  1. The LLM names market labels, specific to broad ("solar panels", "home power equipment", "energy"), plus the need.
  2. Each label is tested in Qloo: semantic tag search, then Qloo brands that carry the tag (hard filter), local then global.
     A label only counts when Qloo returns enough brands that carry the tag.
  3. One batched LLM check judges the brands from all tested labels (this is what rejects "general electronics" for solar).
  4. Every attempt goes into a ledger. If the market is still thin, the LLM is told what came back and must try other labels.
  5. Nothing confirmed -> the result says so; the report then shows the model's view as unconfirmed.

Learned mappings (label -> Qloo tags that worked) can be supplied as `known` and are tried first, with no LLM call
when they already confirm the market. New successes are returned in `learned` for the caller to store.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..modes.business.pipeline import Evidence
from ..qloo import calls, normalize as nz
from ..qloo.client import QlooClient
from .competitors import GENRE_PREFIX, is_brand_tag, tag_matches
from .intake import ProductIntake

MAX_ROUNDS = 2
LABELS_PER_ROUND = 4
TAGS_PER_LABEL = 2
MIN_BRANDS = 3          # Qloo brands carrying the tag, before a label is worth judging
ENOUGH = 3              # confirmed brands (all tiers) at which the ladder stops
KEEP_PER_LABEL = 3
TIERS = ("direct", "alternative", "sector")

MAP_SYSTEM = """You map a product to the market categories where its competition lives, so real brands can be looked up in Qloo, a
taste database of consumer brands (it knows well-known consumer brands, not small firms or business suppliers).
Think about the customer's problem: what else solves it today, even with a different kind of product?
Reply as JSON: {"need": "<the customer's problem, under 12 words>", "labels": [{"label": "<2-4 plain words naming an industry or product type>", "tier": "direct"|"alternative"|"sector"}]}
- direct: same kind of product. alternative: a different product that solves the same problem. sector: the wider industry.
- 5 to 7 labels, ordered from most specific to broadest. Include at least one alternative and one sector.
- Plain generic category words only. No brand names, no product names.
- If "tried" is given, it shows labels already tested and what came back. Never repeat them: use different words or neighbouring
  categories, and learn from the results (for example if a label returned general electronics, go more specific)."""

FIT_SYSTEM = """You judge whether brands found in a Qloo category belong in the competition of a product. Reply as JSON:
{"labels": {"<label>": {"fit": "direct"|"alternative"|"sector"|"none", "keep": ["<brand>", ...], "why": "<under 15 words>"}}}
- direct: the brands sell the same kind of product. alternative: a different product that solves the same customer problem.
  sector: same industry, different product. none: a different market (for example general electronics for a solar panel).
- Judge from the category tags and the brand names and tags given. Keep at most 3 brands per label, only ones that clearly belong,
  with names exactly as given. Be strict: when unsure, answer none."""

_BAD = re.compile(r"[<>{}\[\]\"]")


def clean_labels(parsed: Any, tried: set[str], limit: int = LABELS_PER_ROUND) -> tuple[str, list[dict[str, str]]]:
    """Validate the mapping reply: plain short labels, a known tier, nothing already tried."""
    if not isinstance(parsed, dict):
        return "", []
    need = str(parsed.get("need") or "").strip()[:120]
    out: list[dict[str, str]] = []
    seen = set(tried)
    for it in parsed.get("labels") or []:
        if not isinstance(it, dict):
            continue
        label = re.sub(r"\s+", " ", str(it.get("label") or "")).strip().lower()
        tier = str(it.get("tier") or "").strip().lower()
        if not (2 < len(label) <= 40) or _BAD.search(label) or label in seen:
            continue
        seen.add(label)
        out.append({"label": label, "tier": tier if tier in TIERS else "sector"})
    return need, out[:limit]


def _tag_names(tags: list[dict[str, Any]], limit: int = 4) -> list[str]:
    names: list[str] = []
    for t in tags or []:
        tid = str(t.get("id") or "")
        if tid.startswith(("urn:tag:genre:brand", "urn:tag:industry", "urn:tag:product_service")):
            n = (t.get("name") or tid.rsplit(":", 1)[-1].replace("_", " ")).strip()
            if n and n not in names:
                names.append(n)
    return names[:limit]


async def _test_label(client: QlooClient, intake: ProductIntake, ev: Evidence, label: str,
                      pinned: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Qloo side of one label: candidate tags, then brands carrying the tag. Returns a ledger entry."""
    entry: dict[str, Any] = {"label": label, "tags": [], "brands": [], "scope": None, "evidence": [], "result": "no matching Qloo brand category"}
    if pinned:
        tags = pinned
    else:
        res = await client.call(calls.tags_of_type(f"ladder-tag-{label}", "urn:tag:genre:brand", query=label, take=8, step="resolve", semantic=True))
        found = [t for t in (nz.tags_from_body(res.body) if res.ok else []) if is_brand_tag(t) and t.get("id")]
        entry["evidence"].append(ev.add("resolve", f"ladder tag search: {label}", res, {"query": label, "candidates": found[:8]}))
        order = {id(t): i for i, t in enumerate(found)}
        tags = sorted(found, key=lambda t: (not tag_matches(t.get("name") or "", label), order[id(t)]))[:TAGS_PER_LABEL]
    if not tags:
        return entry
    seen_tags: set[str] = set()
    for tag in tags:
        if tag["id"] in seen_tags:
            continue
        seen_tags.add(tag["id"])
        for loc, scope in ((intake.location, "local"), (None, "global")):
            sig = calls.Signals(filter_tags=[tag["id"]], location=loc)
            res = await client.call(calls.insights_entities("competitors", f"ladder-{label}-{scope}", "brand", sig, take=10,
                                                            explain=False, allow_no_location=False))
            ents = [e for e in (nz.entities_from_insights(res.body) if res.ok else []) if e.get("entity_id") and e.get("name")]
            carry = [e for e in ents if any(str(t.get("id", "")).startswith(tag["id"]) for t in e.get("tags") or [])]
            eid = ev.add("competitors", f"ladder: brands for '{label}' ({tag.get('name')}, {scope})", res,
                         {"label": label, "tag": tag, "scope": scope, "entities": ents[:10], "carry_category": [e["name"] for e in carry]})
            entry["evidence"].append(eid)
            entry["tags"].append({"id": tag["id"], "name": tag.get("name"), "scope": scope, "returned": len(ents), "carry": len(carry)})
            if len(carry) >= MIN_BRANDS:
                entry["brands"] = [{"entity_id": e["entity_id"], "name": e["name"], "tags": e.get("tags") or [], "tag_names": _tag_names(e.get("tags") or []),
                                    "category": tag["id"], "scope": scope, "evidence": eid} for e in carry]
                entry["scope"] = scope
                entry["result"] = f"{len(carry)} brands in '{tag.get('name')}' ({scope})"
                return entry
        entry["result"] = "too few brands in the matching categories"
    return entry


async def _judge(llm: Any, intake: ProductIntake, need: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    """One batched LLM call for every label that returned brands."""
    rows = {e["label"]: {"category_tags": [t["name"] for t in e["tags"] if t.get("name")][:2],
                         "brands": [{"name": b["name"], "tags": b["tag_names"]} for b in e["brands"][:8]]} for e in entries}
    parsed = await llm.chat_json("ladder_fit_check", FIT_SYSTEM,
                                 json.dumps({"product": f"{intake.name}: {intake.description[:240]}", "need": need, "labels": rows}), max_tokens=700)
    verdict = parsed.get("labels") if isinstance(parsed, dict) else None
    return verdict if isinstance(verdict, dict) else {}


def _apply_verdict(entries: list[dict[str, Any]], verdict: dict[str, Any], planned_tier: dict[str, str], have: set[str]) -> list[dict[str, Any]]:
    """Keep only brands the check named and Qloo actually returned; fill the ledger with the outcome."""
    kept: list[dict[str, Any]] = []
    for e in entries:
        v = verdict.get(e["label"]) if isinstance(verdict.get(e["label"]), dict) else {}
        fit = str(v.get("fit") or "none").lower()
        e["fit"] = fit if fit in TIERS else "none"
        e["why"] = str(v.get("why") or "")[:120]
        if e["fit"] == "none":
            e["result"] += "; rejected: " + (e["why"] or "does not belong to this market")
            e["brands_returned"] = [b["name"] for b in e["brands"]]
            e["brands"] = []
            continue
        names = {str(n).lower() for n in (v.get("keep") or []) if isinstance(n, str)}
        picked = [b for b in e["brands"] if b["name"].lower() in names and b["entity_id"] not in have][:KEEP_PER_LABEL]
        e["brands_returned"] = [b["name"] for b in e["brands"]]
        e["brands"] = picked
        e["tier"] = e["fit"]
        for b in picked:
            have.add(b["entity_id"])
            kept.append({**b, "label": e["label"], "tier": e["fit"]})
        e["result"] += f"; kept {len(picked)} as {e['fit']}"
    return kept


def _ledger_view(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"label": e["label"], "tier": e.get("tier") or e.get("fit") or e.get("planned_tier"), "result": e["result"],
             "tags": [t["name"] for t in e["tags"] if t.get("name")][:3], "kept": [b["name"] for b in e["brands"]],
             "returned": e.get("brands_returned", [])[:6], "evidence": e["evidence"]} for e in entries]


async def run_ladder(client: QlooClient, intake: ProductIntake, ev: Evidence, llm: Any, direct_have: list[dict[str, Any]],
                     known: list[dict[str, Any]] | None = None, max_rounds: int = MAX_ROUNDS) -> dict[str, Any]:
    """Returns {"need", "kept": [brands with tier/label/category], "ledger": [...], "learned": [{label, tier, tags}], "notes": [...],
    "confirmed": bool}. `direct_have` are the direct competitors already confirmed (given or found by the fixed steps)."""
    out: dict[str, Any] = {"need": "", "kept": [], "ledger": [], "learned": [], "notes": [], "confirmed": False}
    if llm is None:
        out["notes"].append("The market around the product was not explored (the language model is not available).")
        return out
    have = {a["entity_id"] for a in direct_have}
    have_direct = len(direct_have)
    tried: set[str] = set()
    all_entries: list[dict[str, Any]] = []
    need = ""
    # known mappings first: pinned tags, no LLM mapping call needed when they already fill the market
    pre: list[dict[str, Any]] = []
    for k in (known or [])[:LABELS_PER_ROUND]:
        pre.append({"label": k["label"], "tier": k.get("tier", "sector"), "pinned": k.get("tags") or []})
    try:
        for step in range(max_rounds + (1 if pre else 0)):  # a known-mappings pass does not count as a model round
            if step == 0 and pre:
                plan = pre
            else:
                payload: dict[str, Any] = {"product": {"name": intake.name, "description": intake.description[:300], "category": intake.category,
                                                       "type": intake.product_type or intake.category}, "location": intake.location}
                if all_entries:
                    payload["tried"] = [{"label": e["label"], "result": e["result"], "returned": e.get("brands_returned", [])[:5]} for e in all_entries]
                if have_direct >= 2:
                    payload["note"] = "The direct competitors are already known; give alternative and sector labels."
                parsed = await llm.chat_json("market_map", MAP_SYSTEM, json.dumps(payload), max_tokens=600)
                need_new, plan = clean_labels(parsed, tried)
                need = need or need_new
                if have_direct >= 2:
                    plan = [p for p in plan if p["tier"] != "direct"]
            plan = [p for p in plan if p["label"] not in tried][:LABELS_PER_ROUND]
            if not plan:
                break
            entries = []
            for p in plan:
                tried.add(p["label"])
                e = await _test_label(client, intake, ev, p["label"], pinned=p.get("pinned"))
                e["planned_tier"] = p["tier"]
                entries.append(e)
            all_entries += entries
            judged = [e for e in entries if e["brands"]]
            if judged:
                verdict = await _judge(llm, intake, need, judged)
                out["kept"] += _apply_verdict(judged, verdict, {e["label"]: e["planned_tier"] for e in entries}, have)
            if len(out["kept"]) + have_direct >= ENOUGH:
                break
    except Exception as exc:  # the ladder is an extra: the fixed steps already ran
        out["notes"].append(f"The market search stopped early ({type(exc).__name__}: {str(exc)[:80]}).")
    out["need"] = need
    out["ledger"] = _ledger_view(all_entries)
    out["confirmed"] = bool(out["kept"])
    seen: set[str] = set()
    for e in all_entries:
        if e.get("brands") and e["label"] not in seen:
            seen.add(e["label"])
            out["learned"].append({"label": e["label"], "tier": e.get("tier"), "tags": [{"id": t["id"], "name": t.get("name")} for t in e["tags"] if t["carry"] >= MIN_BRANDS][:2]})
    if not out["kept"]:
        out["notes"].append("No competing or alternative brands could be confirmed for this product's market.")
    return out
