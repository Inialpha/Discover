"""Competitor discovery that works for any product category, with Qloo as the judge.

Sources, in order (each competitor records how it was found; nothing enters the evidence unless Qloo confirms it):
  given          the business listed it; resolved by strict name match in Qloo
  qloo_tag       Qloo tag search for the product type (e.g. "toothpaste"), then Qloo brands for that tag in the location
  llm_confirmed  the LLM suggests brand names for the category and country; kept ONLY if Qloo resolves the exact name
  related        Qloo brands related to the ones found so far, kept only if they share a Qloo tag with them

The LLM never adds a competitor on its own, and a name Qloo cannot confirm is reported as unresolved.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from ..modes.business.pipeline import Evidence
from ..qloo import calls, normalize as nz
from ..qloo.client import QlooClient
from .intake import ProductIntake

DEFAULT_TERMS = {
    "smartphone": ["smartphone", "mobile phone"], "computing": ["laptop", "computer"], "apparel_footwear": ["clothing", "footwear"],
    "education_service": ["education", "online learning"], "beauty_personal_care": ["skincare", "personal care"],
    "food_beverage": ["food", "beverage"], "health_wellness": ["health", "wellness"], "digital_subscription": ["subscription service"],
    "fintech_app": ["fintech", "payments"], "software_saas": ["software", "productivity"], "home_appliance": ["home appliance"],
    "vehicle": ["automobile"], "travel_hospitality": ["travel", "hotel"], "entertainment_media": ["streaming", "entertainment"],
}

LLM_SYSTEM = """You list well-known competitor BRAND NAMES for a product category in a country. Reply as JSON:
{"brands": ["Name", ...]} with at most 8 real brands that sell the same kind of product in that country or are widely
known there. Brand names only: no descriptions, numbers or claims. If unsure, return fewer names."""

_NAME_BAD = re.compile(r"[^\w .&'+-]")


def search_terms(intake: ProductIntake) -> list[str]:
    """Words for the Qloo tag search: the business's own product_type; category defaults only when none was given.
    (Live run: defaults such as "skincare" pulled make-up brands for a toothpaste.)"""
    pt = (intake.product_type or "").strip().lower()
    return [pt] if pt else DEFAULT_TERMS.get(intake.category, [])[:2]


def is_brand_tag(tag: dict[str, Any]) -> bool:
    """Live run: most tags matching a product word are PLACE categories (urn:tag:category:place:mobile_phone) and
    pull unrelated brands (banks). Only brand-genre tags describe brands."""
    return str(tag.get("id") or "").startswith("urn:tag:genre:brand")


GENRE_PREFIX = "urn:tag:genre:brand:"


def genre_paths(tags: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    """Category paths from a brand's own tags. Real ids are hierarchical:
    urn:tag:genre:brand:health_and_beauty -> ('health_and_beauty',); ...:wine_and_spirits:beer -> ('wine_and_spirits','beer').
    Style, lifestyle and wikipedia tags are ignored: live run, a bank and a soap 'shared' a style tag ('Clean')."""
    out = []
    for t in tags or []:
        tid = str(t.get("id") or "")
        if tid.startswith(GENRE_PREFIX) and tid[len(GENRE_PREFIX):]:
            out.append(tuple(tid[len(GENRE_PREFIX):].split(":")))
    return out


def genre_closeness(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> int:
    """Depth of the deepest category path two brands share (0 = different top-level categories)."""
    best = 0
    for pa in genre_paths(a):
        for pb in genre_paths(b):
            n = 0
            for x, y in zip(pa, pb):
                if x != y:
                    break
                n += 1
            best = max(best, n)
    return best


def coherent_brands(ents: list[dict[str, Any]], min_cluster: int = 3) -> list[dict[str, Any]]:
    """Keep brands whose top-level category is shared by at least min_cluster returned brands; [] when none is.
    Stops a random set of location favourites being passed off as competitors."""
    from collections import Counter
    tops = {e.get("entity_id"): {p[0] for p in genre_paths(e.get("tags") or [])} for e in ents}
    count = Counter(t for v in tops.values() for t in v)
    common = {t for t, c in count.items() if c >= min_cluster}
    keep = [e for e in ents if tops.get(e.get("entity_id"), set()) & common]
    return keep if len(keep) >= min_cluster else []


def humanize(tag_id: str) -> str:
    """urn:tag:competitor_brand:qloo:l_oreal_paris -> 'l oreal paris' (name from the id when the record gives none)."""
    return tag_id.rsplit(":", 1)[-1].replace("_", " ").strip()


def profile_from_extras(info: dict[str, Any]) -> dict[str, list[str]]:
    """What a brand record says about itself: competitors, similar brands, customer segments, industries, products.
    Live probe: Tecno -> competitor_brand infinix/oppo/realme/samsung/xiaomi; customer_segment budget_conscious_tech_enthusiasts."""
    def names(ns: str) -> list[str]:
        out: list[str] = []
        for t in info.get("tags") or []:
            tid = str(t.get("id") or "")
            if tid.startswith(f"urn:tag:{ns}:") and tid != f"urn:tag:{ns}:qloo":
                n = (t.get("name") or humanize(tid)).strip()
                if n and n not in out:
                    out.append(n)
        return out
    return {"competitors": names("competitor_brand"), "similar": names("similar_brand"), "segments": names("customer_segment"),
            "industries": names("industry"), "products": names("product_service")}


VERIFY_SYSTEM = """You check whether Qloo brand records describe the right kind of business. Reply as JSON:
{"matches": {"<brand name>": true|false}}. A record matches if its industries/products fit the same market as the product.
A brand with the same name but a different business (for example a university instead of a toothpaste maker) does not match.
Judge only from the fields given. If a record has no industries or products, answer true."""


async def verify_anchors(llm: Any, intake: ProductIntake, profiles: dict[str, dict[str, Any]]) -> tuple[set[str], list[str]]:
    """One LLM call: entity ids whose Qloo record does NOT fit the product's market, plus the reasons (shown in the report)."""
    rows = {pr["name"]: {"industries": pr["industries"][:4], "products": pr["products"][:5], "customer_segments": pr["segments"][:3],
                         "competitors": pr["competitors"][:4]} for pr in profiles.values() if pr["industries"] or pr["products"]}
    if not rows:
        return set(), []
    try:
        parsed = await llm.chat_json("verify_competitor_identity", VERIFY_SYSTEM,
                                     json.dumps({"product": f"{intake.name}: {intake.description[:240]}", "category": intake.product_type or intake.category,
                                                 "records": rows}), max_tokens=500)
    except Exception:
        return set(), []
    verdict = parsed.get("matches") if isinstance(parsed, dict) else None
    bad: set[str] = set()
    why: list[str] = []
    for eid, pr in profiles.items():
        if isinstance(verdict, dict) and verdict.get(pr["name"]) is False:
            bad.add(eid)
            why.append(f"Qloo's record for '{pr['name']}' describes {', '.join((pr['industries'] or pr['products'])[:3])}, "
                       "not this product's market, so it was not used.")
    return bad, why



def tag_matches(tag_name: str, term: str) -> bool:
    """A Qloo tag fits a search term when every word of the term appears in the tag name (singular/plural tolerant)."""
    def stem(w: str) -> str:
        return w[:-1] if len(w) > 3 and w.endswith("s") else w
    tw = {stem(w) for w in re.split(r"[^a-z0-9]+", (tag_name or "").lower()) if w}
    qw = [stem(w) for w in re.split(r"[^a-z0-9]+", term.lower()) if w]
    return bool(qw) and all(w in tw for w in qw)


def category_candidates(anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Category tag ids that most anchors share, deepest first. Live run: Qloo's own tags on a brand name its categories
    (Tecno: Electronics > Phones & Tablets; Nivea: Health & Beauty), so one confirmed brand points to its category."""
    from collections import Counter
    n = len(anchors)
    count: Counter = Counter()
    for a in anchors:
        prefixes = {p[:i] for p in genre_paths(a.get("tags") or []) for i in range(1, len(p) + 1)}
        count.update(prefixes)
    need = max(1, (n + 1) // 2)
    cands = [{"id": GENRE_PREFIX + ":".join(p), "depth": len(p), "anchors": c} for p, c in count.items() if c >= need]
    return sorted(cands, key=lambda c: (-c["depth"], -c["anchors"], c["id"]))


def clean_llm_names(parsed: Any, limit: int = 8) -> list[str]:
    raw = parsed.get("brands") if isinstance(parsed, dict) else parsed if isinstance(parsed, list) else []
    out: list[str] = []
    for n in raw or []:
        if isinstance(n, str) and not re.search(r"[<>{}\[\]]", n):
            n = _NAME_BAD.sub("", n).strip()
            if 1 < len(n) <= 40 and n.lower() not in {x.lower() for x in out}:
                out.append(n)
    return out[:limit]


async def _resolve(client: QlooClient, names: list[str], source: str, ev: Evidence, pick_anchor: Any) -> tuple[list[dict], list[str]]:
    specs = [calls.search_entities(f"brand-{n}", n, "brand", take=5) for n in names]
    results = await asyncio.gather(*(client.call(s) for s in specs))
    found: list[dict] = []
    missing: list[str] = []
    for name, res in zip(names, results):
        cands = nz.entities_from_search(res.body) if res.ok else []
        top, how = pick_anchor(cands, name)
        ev.add("resolve", f"brand:{name}", res, {"query": name, "kind": "brand", "candidates": cands[:5], "chosen": top,
                                                 "matched_by": how, "source": source})
        if top:
            found.append({"query": name, "entity_id": top["entity_id"], "name": top["name"], "matched_by": how,
                          "source": source, "tags": top.get("tags") or []})
        else:
            missing.append(name)
    return found, missing


async def discover_competitors(client: QlooClient, intake: ProductIntake, ev: Evidence, pick_anchor: Any, llm: Any = None,
                               want: int = 5, discover: bool = True) -> dict[str, Any]:
    anchors: list[dict] = []
    unresolved: list[str] = []
    notes: list[str] = []

    def add(items: list[dict]) -> None:
        have = {a["entity_id"] for a in anchors}
        for it in items:
            if it["entity_id"] not in have and len(anchors) < want:
                anchors.append(it)
                have.add(it["entity_id"])

    if intake.competitors:
        found, missing = await _resolve(client, intake.competitors, "given", ev, pick_anchor)
        add(found)
        unresolved += missing
    if not discover:
        return {"anchors": anchors, "unresolved": unresolved, "notes": notes, "category": None}

    # the business's own list wins: with two or more resolved competitors, do not add guesses
    need_more = len(anchors) < 2
    # 2) LLM suggestions, verified by Qloo
    if need_more and len(anchors) < want and llm is not None:
        try:
            parsed = await llm.chat_json("competitor_suggestions", LLM_SYSTEM,
                                         f"Product type: {intake.product_type or intake.category}\nCategory: {intake.category}\n"
                                         f"Country: {intake.market.name if intake.market else intake.location}\n"
                                         f"Product: {intake.name}: {intake.description[:300]}", max_tokens=600)
            names = [n for n in clean_llm_names(parsed)
                     if n.lower() not in {a["name"].lower() for a in anchors} and n.lower() not in {u.lower() for u in unresolved}]
        except Exception as exc:  # LLM is optional; discovery continues without it
            names = []
            notes.append(f"LLM competitor suggestions unavailable ({type(exc).__name__}).")
        if names:
            found, missing = await _resolve(client, names, "llm_confirmed", ev, pick_anchor)
            add(found)
            if missing:
                notes.append(f"LLM suggested brands Qloo could not confirm, so they were not used: {', '.join(missing)}.")

    # 1) Qloo category route: find a brand category (genre:brand tag) matching the product type, then a HARD tag filter.
    #    Live run: filter.tags returned 8/8 skincare brands for Lagos; the soft signal returned 0/10.
    if len(anchors) < 2:
        for term in search_terms(intake):
            res = await client.call(calls.tags_of_type(f"tag-{term}", "urn:tag:genre:brand", query=term, take=10, step="resolve", semantic=True))
            tags = nz.tags_from_body(res.body) if res.ok else []
            hit = next((t for t in tags if is_brand_tag(t) and tag_matches(t.get("name") or "", term)), None)
            ev.add("resolve", f"tag:{term}", res, {"query": term, "kind": "tag", "candidates": tags[:8], "chosen": hit})
            if not hit:
                continue
            sig = calls.Signals(filter_tags=[hit["id"]], location=intake.location)
            res2 = await client.call(calls.insights_entities("competitors", f"brands-for-tag-{term}", "brand", sig, take=10,
                                                             explain=False, allow_no_location=False))
            ents = [e for e in (nz.entities_from_insights(res2.body) if res2.ok else []) if e.get("entity_id") and e.get("name")]
            carry = [e for e in ents if any(str(t.get("id", "")).startswith(hit["id"]) for t in e.get("tags") or [])]
            ev.add("competitors", f"brands for tag {hit.get('name')}", res2,
                   {"tag": hit, "entities": ents[:10], "carry_category": [e["name"] for e in carry]})
            if len(carry) < 3:
                notes.append(f"Qloo returned too few brands in the category '{hit.get('name')}' for {intake.location}.")
                continue
            add([{"query": term, "entity_id": e["entity_id"], "name": e["name"], "matched_by": "tag", "source": "qloo_tag",
                  "tags": e.get("tags") or []} for e in carry])
            if len(anchors) >= want:
                break
        if not any(a["source"] == "qloo_tag" for a in anchors):
            notes.append("Qloo has no brand category matching the product type; competitors came from other sources.")

    # 3a) Competitors Qloo lists on the brand records themselves (tags urn:tag:competitor_brand:qloo:<name>, plus similar_brand),
    #     each name confirmed by a strict search. Live probe: Tecno -> Infinix, Oppo, Realme, Samsung, Xiaomi.
    profiles: dict[str, dict[str, Any]] = {}

    async def profile(a: dict) -> dict[str, Any]:
        if a["entity_id"] not in profiles:
            res = await client.call(calls.entity_by_id(f"entity-{a['name']}", a["entity_id"]))
            pr = profile_from_extras(nz.entity_extras(res.body) if res.ok else {})
            pr["name"] = a["name"]
            ev.add("brand_profile", f"Qloo record: {a['name']}", res, pr)
            profiles[a["entity_id"]] = pr
        return profiles[a["entity_id"]]

    if 0 < len(anchors) < want:
        names: list[str] = []
        for a in anchors[:3]:
            pr = await profile(a)
            for n in pr["competitors"] + pr["similar"]:
                if n not in names:
                    names.append(n)
        skip = {a["name"].lower() for a in anchors} | {u.lower() for u in unresolved}
        names = [n for n in names if n.lower() not in skip][:8]
        if names:
            found, missing = await _resolve(client, names, "qloo_competitor_tags", ev, pick_anchor)
            add(found)

    # 3b) Qloo brands in the same category, ranked by similarity to our anchors (hard tag filter + anchor signal).
    #     Live probe: category alone returned hair salons and make-up artists for a toothpaste (broad category); with the anchor
    #     as a signal it returned Crest, Sensodyne, Oral-B, Listerine. Category-only results are never used.
    category_used: dict[str, Any] | None = None
    if 0 < len(anchors) < want:
        room = want - len(anchors)
        for cand in category_candidates(anchors)[:3]:
            have_ids = {a["entity_id"] for a in anchors}
            best: tuple[str, list[dict[str, Any]]] | None = None
            for loc, label in ((intake.location, "local"), (None, "global")):
                sig = calls.Signals(filter_tags=[cand["id"]], entities=[a["entity_id"] for a in anchors], location=loc)
                res = await client.call(calls.insights_entities("competitors", f"category-peers-{label}", "brand", sig, take=10,
                                                                explain=False, allow_no_location=False))
                ents = [e for e in (nz.entities_from_insights(res.body) if res.ok else [])
                        if e.get("entity_id") and e.get("name") and e["entity_id"] not in have_ids]
                carry = [e for e in ents if any(str(t.get("id", "")).startswith(cand["id"]) for t in e.get("tags") or [])]
                ev.add("competitors", f"category peers {cand['id'].split(':', 3)[-1]} ({label}, ranked by similarity)", res,
                       {"category": cand["id"], "scope": label, "entities": ents[:10], "carry_category": [e["name"] for e in carry]})
                if len(carry) >= 3:
                    best = (label, carry)
                    break
            if not best:
                continue
            label, carry = best
            category_used = {"id": cand["id"], "scope": label, "depth": cand["depth"], "added": True,
                             "peers": [e["name"] for e in carry]}
            add([{"query": cand["id"], "entity_id": e["entity_id"], "name": e["name"], "matched_by": "category",
                  "source": "qloo_category", "tags": e.get("tags") or [], "category": cand["id"], "scope": label}
                 for e in carry[:room]])
            if label == "global":
                notes.append(f"Qloo has no brands for category '{cand['id'].split(':', 3)[-1]}' in {intake.location}; "
                             "brands from outside the location were used.")
            break
        if not category_used:
            notes.append("Qloo returned too few brands in the competitors' category to add peers.")

    # 4) related brands in the same category, only if the category route added nothing
    if 0 < len(anchors) < want and not category_used:
        sig = calls.Signals(entities=[a["entity_id"] for a in anchors], location=intake.location)
        res = await client.call(calls.insights_entities("competitors", "related-brands", "brand", sig, take=10, explain=False,
                                                        allow_no_location=True))
        ents = nz.entities_from_insights(res.body) if res.ok else []
        keep = []
        for e in ents:
            if not (e.get("entity_id") and e.get("name")):
                continue
            depth = max((genre_closeness(a.get("tags", []), e.get("tags") or []) for a in anchors), default=0)
            if depth >= 1:
                keep.append({"query": e["name"], "entity_id": e["entity_id"], "name": e["name"], "matched_by": "related",
                             "source": "related", "tags": e.get("tags") or [], "category_depth": depth})
        keep.sort(key=lambda k: -k["category_depth"])
        ev.add("competitors", "related brands (same Qloo category)", res, {"entities": ents[:10], "kept": [k["name"] for k in keep]})
        add(keep)
    # 5) identity check: a brand name can be a different Qloo entity (live probe: "Colgate" is Colgate University)
    if anchors and llm is not None:
        for a in anchors:
            await profile(a)
        bad, why = await verify_anchors(llm, intake, {a["entity_id"]: profiles[a["entity_id"]] for a in anchors})
        if bad:
            for a in anchors:
                if a["entity_id"] in bad:
                    unresolved.append(a["query"] if a["source"] == "given" else a["name"])
            anchors[:] = [a for a in anchors if a["entity_id"] not in bad]
            notes += why
    if not anchors:
        notes.append("No competitor could be found in Qloo; audience skew is unavailable and ranking uses rules only.")
    return {"anchors": anchors, "unresolved": unresolved, "notes": notes, "category": category_used,
            "profiles": {a["name"]: profiles[a["entity_id"]] for a in anchors if a["entity_id"] in profiles}}
