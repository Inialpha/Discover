"""Lean competitor discovery: few Qloo calls, one cheap LLM choice, and the choice is always checked against Qloo's data.

Qloo calls (this part of a run: 6 to 9):
  1. resolve the competitors the business listed (one search each), then ONE call for their full records (identity check)
  2. ONE insights call for brands similar to them (hard category filter + the competitors as signals + the location),
     which also returns each brand's full record, including the text describing its audience
  3. only when the business listed no competitor: a tag search for the product type, then ONE insights call for that category

LLM calls (small, names and ids only):
  - identity check of the competitors found by name, read from Qloo's full record of each (live: "Colgate" is also a university)
  - ONE selection call: the product and up to 10 candidate brands (id, name, a line about them, category tags) go in, the ids of the
    ones that really are similar to the product come out. Banks and make-up brands that Qloo links to a toothpaste are dropped
    here. Ids that were not offered are discarded, so the LLM can only choose among brands Qloo returned.

Without an LLM the candidates that share the competitors' Qloo category are used instead.
"""

from __future__ import annotations

import json
from typing import Any

from ..modes.business.pipeline import Evidence
from ..qloo import calls, normalize as nz
from ..qloo.client import QlooClient
from .competitors import (LLM_SYSTEM, _resolve, category_candidates, clean_llm_names, is_brand_tag, profile_from_extras, search_terms,
                          tag_matches, verify_anchors)
from .intake import ProductIntake

MARKET = "Market"  # evidence "segment" label for results that describe the product's whole market, not one buyer segment
MAX_CANDIDATES = 20  # one Qloo call returns this many; each costs the LLM only a short card
PICK = 5  # most similar brands kept
ABOUT_WORDS = 12  # the line about each candidate is cut by words; ids are sent in full

SELECT_SYSTEM = """You choose which brands are most similar to a product. Reply as JSON: {"similar": ["<id>", ...]}.
Input: the product (name, description, type, country) and candidate brands, each with an id, a name, a short line about it and
category tags. Return the ids of at most N candidates (N is given) that sell the same kind of product to the same kind of
buyer, so a customer could choose them instead of the product. Most similar first. Leave out brands from a different
industry (banks, universities, make-up for a toothpaste, and so on). Use only ids from the list. If none qualify, return []."""


def card(e: dict[str, Any]) -> dict[str, Any]:
    """What the LLM sees about a candidate: no more than an id, a name, one short line and three category names."""
    p = e.get("properties") or {}
    about = p.get("short_description") or p.get("description") or e.get("disambiguation") or ""
    tags = [t.get("name") for t in e.get("tags") or [] if str(t.get("id", "")).startswith("urn:tag:genre:") and t.get("name")]
    return {"id": e["entity_id"], "name": e["name"], "about": " ".join(str(about).split()[:ABOUT_WORDS]), "tags": tags[:3]}


async def select_similar(llm: Any, intake: ProductIntake, candidates: list[dict[str, Any]], limit: int) -> list[str] | None:
    """Ids of the candidates the LLM judges most similar to the product; None when the LLM is unavailable or failed."""
    if llm is None or not candidates or limit <= 0:
        return None
    ids = {c["entity_id"] for c in candidates}
    try:
        parsed = await llm.chat_json(
            "select_similar_brands", SELECT_SYSTEM,
            json.dumps({"product": {"name": intake.name, "description": intake.description[:300], "type": intake.product_type or intake.category,
                                    "country": intake.market.name if intake.market else intake.location},
                        "N": limit, "candidates": [card(c) for c in candidates[:MAX_CANDIDATES]]}, ensure_ascii=False, separators=(",", ":")),
            max_tokens=400)
    except Exception:
        return None
    raw = parsed.get("similar") if isinstance(parsed, dict) else None
    if not isinstance(raw, list):
        return None
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and x in ids and x not in out:
            out.append(x)
    return out[:limit]


def _search_profile(a: dict[str, Any]) -> dict[str, Any]:
    """A brand search hit as the record the identity check reads: its disambiguation line and tag names."""
    names = [t.get("name") for t in a.get("tags") or [] if t.get("name")]
    lead = [a["disambiguation"]] if a.get("disambiguation") else []
    return {"name": a["name"], "industries": (lead + names)[:6], "products": [], "segments": [], "competitors": []}


async def _records(client: QlooClient, ev: Evidence, anchors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """What Qloo's own record says each brand is (industries, products, segments, competitors), for the identity check.
    The search hit only carries a dozen tags and is not enough: live run, "Colgate" (the university) listed "Health & Beauty" next to
    architecture styles and was accepted; its full record lists Higher Education and degree programmes. ONE call for all brands;
    a brand missing from the answer is fetched on its own."""
    ids = [a["entity_id"] for a in anchors]
    res = await client.call(calls.entities_by_ids("records-" + "-".join(a["name"] for a in anchors)[:60], ids))
    by_id: dict[str, dict[str, Any]] = {}
    body = res.body if res.ok else None
    rows = body.get("results") if isinstance(body, dict) else None
    rows = rows.get("entities") if isinstance(rows, dict) else rows
    for e in rows or []:
        if isinstance(e, dict) and e.get("entity_id") in ids:
            by_id[e["entity_id"]] = profile_from_extras(nz.entity_extras({"results": [e]}))
    for a in anchors:
        if a["entity_id"] not in by_id:
            one = await client.call(calls.entity_by_id(f"record-{a['name']}", a["entity_id"]))
            if one.ok:
                by_id[a["entity_id"]] = profile_from_extras(nz.entity_extras(one.body))
    out: dict[str, dict[str, Any]] = {}
    for a in anchors:
        pr = by_id.get(a["entity_id"]) or _search_profile(a)  # no record at all: judge from the search hit
        pr["name"] = a["name"]
        out[a["entity_id"]] = pr
        ev.add("brand_profile", f"Qloo record: {a['name']}", res, pr)
    return out


TAG_COMPETITORS = 2  # most competitor names read off the listed brands' own Qloo tags


def tag_competitor_names(anchors: list[dict[str, Any]], limit: int = TAG_COMPETITORS) -> list[str]:
    """Qloo's own brand tags name competitors (Crest and Sensodyne both carry urn:tag:competitor_brand:qloo:colgate). Those names that
    are not already among the anchors, most shared first."""
    from collections import Counter
    have = {_norm(a["name"]) for a in anchors} | {_norm(a.get("query", "")) for a in anchors}
    count: Counter = Counter()
    label: dict[str, str] = {}
    for a in anchors:
        for t in a.get("tags") or []:
            tid = str(t.get("id") or "")
            if tid.startswith("urn:tag:competitor_brand:") and t.get("name") and _norm(t["name"]) not in have:
                count[_norm(t["name"])] += 1
                label.setdefault(_norm(t["name"]), t["name"])
    return [label[k] for k, _ in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def _norm(t: str) -> str:
    return "".join(ch for ch in str(t).lower() if ch.isalnum())


def _deeper_from_anchors(anchors: list[dict[str, Any]], base: dict[str, Any] | None) -> dict[str, Any] | None:
    """A narrower category already on one of the brands' own tags, under the shared one (Colgate: health_and_beauty:oral_care).
    Free: no call. Only when every brand in the narrower category is also in the broad one, which is how the ids are built."""
    if not base:
        return None
    best = None
    for a in anchors:
        for t in a.get("tags") or []:
            tid = str(t.get("id") or "")
            if tid.startswith(base["id"] + ":") and is_brand_tag(t) and (best is None or len(tid) > len(best["id"])):
                best = {"id": tid, "name": t.get("name"), "depth": len(tid.split(":")) - 3}
    return best


async def _deeper_category(client: QlooClient, intake: ProductIntake, ev: Evidence, base: dict[str, Any] | None) -> dict[str, Any] | None:
    """The competitors usually share only a broad Qloo category (Crest and Sensodyne: health_and_beauty), and a broad filter returns
    skincare, pain relief and hair care next to the toothpastes (live run, New York: 1 oral-care brand in 10). A semantic search of Qloo's
    brand categories for the product type finds the narrow one (health_and_beauty:oral_care). It is used only when it sits UNDER the
    competitors' own category, so a loose semantic match can never move the search into another industry."""
    if not base:
        return None
    for term in search_terms(intake):
        res = await client.call(calls.tags_of_type(f"tag-{term}", "urn:tag:genre:brand", query=term, take=10, step="resolve", semantic=True))
        tags = nz.tags_from_body(res.body) if res.ok else []
        under = [t for t in tags if is_brand_tag(t) and str(t.get("id", "")).startswith(base["id"] + ":")]
        ev.add("resolve", f"deeper category for {term}", res, {"query": term, "kind": "tag", "candidates": tags[:8], "chosen": under[0] if under else None})
        if under:
            return {"id": under[0]["id"], "name": under[0].get("name"), "depth": len(under[0]["id"].split(":")) - 3}
    return None


async def _peers(client: QlooClient, intake: ProductIntake, ev: Evidence, anchors: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Any, dict[str, Any]]:
    """Brands similar to the anchors (category filter when they share one). Returns (candidates, call result, meta)."""
    have = {a["entity_id"] for a in anchors}
    ids = [a["entity_id"] for a in anchors][:6]
    cat = (category_candidates(anchors) or [None])[0]
    cat = _deeper_from_anchors(anchors, cat) or (await _deeper_category(client, intake, ev, cat)) or cat
    tries = [(intake.location, "local"), (None, "global")] if cat else [(intake.location, "local")]
    last: tuple[list[dict[str, Any]], Any, dict[str, Any]] = ([], None, {})
    for loc, scope in tries:
        sig = calls.Signals(filter_tags=[cat["id"]] if cat else [], entities=ids, location=loc)
        res = await client.call(calls.insights_entities("competitors", f"similar-brands-{scope}", "brand", sig, take=MAX_CANDIDATES,
                                                        explain=False, allow_no_location=loc is None))
        ents = [e for e in (nz.entities_from_insights(res.body) if res.ok else []) if e.get("entity_id") and e.get("name") and e["entity_id"] not in have]
        carry = [e for e in ents if cat and any(str(t.get("id", "")).startswith(cat["id"]) for t in e.get("tags") or [])]
        meta = {"category": cat["id"] if cat else None, "scope": scope, "carry_category": [e["name"] for e in carry]}
        last = (ents, res, meta)
        if len(carry if cat else ents) >= 3:
            break
    return last


async def discover_lean(client: QlooClient, intake: ProductIntake, ev: Evidence, pick_anchor: Any, llm: Any = None,
                        want: int = 5, discover: bool = True) -> dict[str, Any]:
    anchors: list[dict[str, Any]] = []
    unresolved: list[str] = []
    notes: list[str] = []

    def add(items: list[dict[str, Any]]) -> None:
        have = {a["entity_id"] for a in anchors}
        for it in items:
            if it["entity_id"] not in have:
                anchors.append(it)
                have.add(it["entity_id"])

    if intake.competitors:
        found, missing = await _resolve(client, intake.competitors[:4], "given", ev, pick_anchor)
        add(found)
        unresolved += missing
    if not discover:
        return {"anchors": anchors, "unresolved": unresolved, "notes": notes, "category": None}

    # competitors Qloo itself names on the listed brands (2 search calls); the identity check below applies to them too
    tagged = tag_competitor_names(anchors) if anchors else []
    if tagged:
        found, _missing = await _resolve(client, tagged, "qloo_competitor_tags", ev, pick_anchor)
        add(found)

    # nothing resolved: start from Qloo's own category for the product type (2 calls, no name lookups)
    if not anchors:
        for term in search_terms(intake):
            res = await client.call(calls.tags_of_type(f"tag-{term}", "urn:tag:genre:brand", query=term, take=10, step="resolve", semantic=True))
            tags = nz.tags_from_body(res.body) if res.ok else []
            hit = next((t for t in tags if is_brand_tag(t) and tag_matches(t.get("name") or "", term)), None)
            ev.add("resolve", f"tag:{term}", res, {"query": term, "kind": "tag", "candidates": tags[:8], "chosen": hit})
            if not hit:
                continue
            res2 = await client.call(calls.insights_entities("competitors", f"brands-for-tag-{term}", "brand",
                                                             calls.Signals(filter_tags=[hit["id"]], location=intake.location),
                                                             take=MAX_CANDIDATES, explain=False, allow_no_location=False))
            ents = [e for e in (nz.entities_from_insights(res2.body) if res2.ok else []) if e.get("entity_id") and e.get("name")]
            carry = [e for e in ents if any(str(t.get("id", "")).startswith(hit["id"]) for t in e.get("tags") or [])]
            chosen_ids = await select_similar(llm, intake, carry, want)
            picked = [e for e in carry if e["entity_id"] in (chosen_ids if chosen_ids is not None else [x["entity_id"] for x in carry[:want]])]
            ev.add("competitors", f"brands for tag {hit.get('name')}", res2,
                   {"tag": hit, "entities": ents[:MAX_CANDIDATES], "carry_category": [e["name"] for e in carry], "selected": [e["name"] for e in picked]})
            if len(carry) >= 3 and picked:
                add([{"query": term, "entity_id": e["entity_id"], "name": e["name"], "matched_by": "tag", "source": "qloo_tag",
                      "tags": e.get("tags") or [], "entity": e} for e in picked[:want]])
                break
            notes.append(f"Qloo returned too few brands in the category '{hit.get('name')}' for {intake.location}.")

    # still nothing: ask the LLM for brand names and keep only those Qloo confirms by exact name
    if not anchors and llm is not None:
        try:
            parsed = await llm.chat_json("competitor_suggestions", LLM_SYSTEM,
                                         f"Product type: {intake.product_type or intake.category}\nCategory: {intake.category}\n"
                                         f"Country: {intake.market.name if intake.market else intake.location}\n"
                                         f"Product: {intake.name}: {intake.description[:300]}", max_tokens=600)
            names = [n for n in clean_llm_names(parsed) if n.lower() not in {u.lower() for u in unresolved}][:4]
        except Exception as exc:
            names = []
            notes.append(f"LLM competitor suggestions unavailable ({type(exc).__name__}).")
        if names:
            found, missing = await _resolve(client, names, "llm_confirmed", ev, pick_anchor)
            add(found)
            if missing:
                notes.append(f"LLM suggested brands Qloo could not confirm, so they were not used: {', '.join(missing)}.")

    # identity check for brands found by name (never for brands that came through a Qloo category)
    named = [a for a in anchors if a["source"] in ("given", "llm_confirmed", "qloo_competitor_tags")]
    profiles: dict[str, dict[str, Any]] = {}
    if named and llm is not None:
        profiles = await _records(client, ev, named)
        bad, why = await verify_anchors(llm, intake, profiles)
        if bad:
            for a in named:
                if a["entity_id"] in bad and a["source"] != "qloo_competitor_tags":
                    unresolved.append(a["query"] if a["source"] == "given" else a["name"])
            anchors[:] = [a for a in anchors if a["entity_id"] not in bad]
            notes.extend(why)

    # similar brands: one call, then the LLM keeps the ones that really fit the product
    selected: list[dict[str, Any]] = []
    peers_res: Any = None
    if anchors and len(anchors) < want + 3 and not any(a["source"] == "qloo_tag" for a in anchors):
        ents, peers_res, meta = await _peers(client, intake, ev, anchors)
        cat = meta.get("category")
        pool = [e for e in ents if not cat or any(str(t.get("id", "")).startswith(cat) for t in e.get("tags") or [])] or []
        room = PICK
        chosen_ids = await select_similar(llm, intake, pool, room)
        selected = [e for e in pool if e["entity_id"] in chosen_ids] if chosen_ids is not None else pool[:room]
        if chosen_ids is not None:  # keep the LLM's order
            order = {x: i for i, x in enumerate(chosen_ids)}
            selected.sort(key=lambda e: order[e["entity_id"]])
        ev.add("competitors", f"similar brands ({meta.get('scope')}, category filter + competitors as signals)", peers_res,
               {**meta, "entities": ents[:MAX_CANDIDATES], "selected": [e["name"] for e in selected]})
        if meta.get("scope") == "global" and selected:
            notes.append("Qloo has no similar brands in this location; brands from outside it were used.")
        add([{"query": a["name"], "entity_id": e["entity_id"], "name": e["name"], "matched_by": "similar", "source": "qloo_similar",
              "tags": e.get("tags") or [], "entity": e} for a in anchors[:1] for e in selected])
        if not selected:
            notes.append("Qloo returned no similar brands that fit the product; only the competitors listed were used.")
    similar_entities = [a["entity"] for a in anchors if a["source"] in ("qloo_similar", "qloo_tag") and a.get("entity")]
    if similar_entities:
        # the full records of the chosen brands feed the culture digest (never shown as "tastes")
        probe = peers_res if peers_res is not None else _FakeOk()
        ev.add("affinity", "market:brand (similar brands)", probe, {"kind": "brand", "anchored": True, "entities": similar_entities}, MARKET)
    if not anchors:
        notes.append("No competitor could be found in Qloo; audience skew is unavailable and ranking uses rules only.")
    for a in anchors:
        a.pop("entity", None)
    return {"anchors": anchors, "unresolved": unresolved, "notes": notes, "category": None,
            "profiles": {a["name"]: profiles[a["entity_id"]] for a in anchors if a["entity_id"] in profiles}}


class _FakeOk:
    """Stands in for a call result when the entities came from an earlier call already recorded in the evidence."""
    ok, error, skipped_reason, status, files, meta = True, None, None, 200, [], {}
