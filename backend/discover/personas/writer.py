"""Persona cards: one LLM call per persona (small prompts fit tight token-per-minute limits), strict validation,
and a deterministic template when the LLM is missing or fails.

Every claim carries a `basis`:
  evidence        cites Qloo evidence ids that exist in this run
  calculated      computed from cited statistics (price vs income bands)
  interpretation  the model's reasoning; never presented as data
Names of places and tastes are only kept if Qloo actually returned them for that segment. Platforms and events are
always interpretation (Qloo has no platform or event data).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from ..llm.client import LLMClient, LLMError
from .affordability import Affordability
from .evidence import entity_names, place_affinity, place_names, segment_view
from .intake import ProductIntake
from .scoring import SegmentScore

PERSONA_SYSTEM = """You write ONE buyer persona for a business, using ONLY the JSON you are given. Reply with one JSON object:
{"segment_id": str, "name": str, "headline": str, "who": str,
 "motivations": [{"text": str, "basis": "evidence"|"interpretation", "evidence": [ids]}],
 "objections": [{"text": str, "basis": "interpretation", "evidence": [ids]}],
 "messages": [{"angle": str, "text": str, "basis": "evidence"|"interpretation", "evidence": [ids]}],
 "platforms": [{"platform": str, "why": str}],
 "where_to_reach": [{"place": str, "evidence": [ids]}],
 "tastes": [{"name": str, "kind": str, "evidence": [ids]}],
 "events": [{"idea": str, "why": str}],
 "caveats": [str]}
Rules:
- Evidence ids look like E012 and appear in the input. Cite them in "evidence" for every claim about tastes or places.
  If a claim has no evidence id, its basis must be "interpretation".
- "name" is a short descriptor of the persona (for example "Budget-minded student"); no first name, no real person.
- "who" paraphrases the segment's description and age bands only. Do not invent a specific age, gender, job, employer,
  income, family situation or personal story.
- Never state a number, percentage, population size or market share that is not in the input. Qloo scores and indexes
  are RELATIVE; say "skews toward", never "X% of".
- Price statements may only use the "affordability" and "reach" fields; the computed price barriers are added by the system,
  so your objections are interpretation.
- "messages" are the model's marketing ideas (always interpretation). Put the evidence ids of a taste that inspired a
  message in "evidence", but never claim the product has a feature, partnership or similarity to a brand that the
  product text does not state, and never call a brand "top-rated" or "trusted".
- "tastes" and "where_to_reach" may only use names that appear in the input's qloo lists. Do not describe what a place
  is like. Never name districts or neighbourhoods; areas may only be described as "near <place name>" from
  qloo.areas.named_by_nearby_place.
- Never invent product specs or numbers (hours of battery, megapixels, storage, speeds). Use only what the product text
  states. Never use comparatives or social proof ("outlasts", "best", "top-rated", "chosen by", "trusted by", "fans of").
- If an item looks foreign to the market (for example an artist from another country), you may list it but say it is cross-market.
- "platforms" and "events" are interpretation: Qloo has no platform or event data. At most 3 platforms and 2 events.
- At most 3 messages (each under 25 words), 3 motivations, 3 objections. Messages must rest on a product fact in the input
  or a cited taste; do not promise features the product text does not state.
- If qloo data is missing for something, say so in "caveats" instead of filling the gap."""


def _norm(t: str) -> str:
    return "".join(ch for ch in (t or "").lower() if ch.isalnum())


# Real run: the model invented "40 hrs on a single charge", "outlasts the competition" and "chosen by fans of ...".
UNSUPPORTED_PHRASES = ("outlast", "best-selling", "best selling", "top-rated", "top rated", "#1", "number one", "guaranteed",
                       "unbeatable", "chosen by", "trusted by", "loved by", "fans of", "most popular", "market leader")
FEATURE_WORDS = ("battery", "camera", "storage", "processor", "performance", "gaming", "display", "screen", "waterproof",
                 "charging", "memory", "5g", "signal", "network", "fast", "speed", "durable", "warranty", "hours", "hrs",
                 "fluoride", "whitening", "sensitive", "natural", "organic", "vegan", "spf", "hypoallergenic", "dermatologist",
                 "clinically", "fragrance", "moisturising", "moisturizing", "encrypted", "encryption", "secure", "ats",
                 "templates", "integration", "instant", "free", "unlimited", "ai", "automatic")
_NUM = re.compile(r"\d[\d,]*\.?\d*")


def _num_norm(n: str) -> str:
    return n.replace(",", "").rstrip(".")


def product_text(intake: ProductIntake) -> str:
    return " ".join([intake.name, intake.description, *intake.features]).lower()


def allowed_numbers(intake: ProductIntake) -> set[str]:
    nums = {_num_norm(n) for n in _NUM.findall(product_text(intake))}
    nums |= {"18", "24", "25", "29", "30", "34", "35", "44", "45", "54", "55"}  # the age bands themselves
    nums |= {f"{intake.price:g}", str(int(intake.price)) if float(intake.price).is_integer() else str(intake.price)}
    return {n for n in nums if n}


def _has_word(text: str, w: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text) is not None


def screen_claim(text: str, intake: ProductIntake) -> tuple[bool, list[str]]:
    """(drop, verify_words): drop when the text has numbers the product text doesn't contain or unsupported social
    proof/comparatives; verify_words are feature words the product text does not state (flagged, not dropped)."""
    low = text.lower()
    if any(ph in low for ph in UNSUPPORTED_PHRASES):
        return True, []
    allowed = allowed_numbers(intake)
    numeric_text = re.sub(r"(?<![a-z0-9])[2345]g(?![a-z0-9])", " ", low)  # network generations are feature words, not specs
    if any(_num_norm(n) not in allowed for n in _NUM.findall(numeric_text) if _num_norm(n)):
        return True, []
    ptext = product_text(intake)
    return False, [w for w in FEATURE_WORDS if _has_word(low, w) and not _has_word(ptext, w)]


def names_by_id(ev_items: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for it in ev_items:
        if not it.get("ok"):
            continue
        d = it.get("data") or {}
        if it["step"] == "affinity":
            out[it["id"]] = [e["name"] for e in d.get("entities", []) if e.get("name")]
        elif it["step"] == "resolve" and d.get("chosen"):
            out[it["id"]] = [d["chosen"].get("name")]
    return out


def skew_summary(age_index: dict[str, float], gender_index: dict[str, float]) -> str:
    if not age_index:
        return ""
    ranked = sorted(age_index.items(), key=lambda kv: -kv[1])
    top = ", ".join(f"{k} ({v:+.2f})" for k, v in ranked[:2])
    low = ", ".join(f"{k} ({v:+.2f})" for k, v in ranked[-1:])
    g = ""
    if gender_index:
        k, v = max(gender_index.items(), key=lambda kv: abs(kv[1]))
        g = f" Leans {k} ({v:+.2f})." if abs(v) >= 0.2 else " No strong gender lean."
    return f"Strongest skew: {top}. Weakest: {low}.{g}"


def price_barriers(seg: SegmentScore, aff: Affordability) -> list[dict[str, Any]]:
    """Objections computed from the numbers (basis 'calculated'); no model involved."""
    out: list[dict[str, Any]] = []
    for q, reach in seg.reach.items():
        if reach in ("stretch", "out_of_reach"):
            band = next((x for x in aff.quintiles if x.quintile == q), None)
            if band and band.ratio is not None:
                word = "a stretch" if reach == "stretch" else "out of reach"
                out.append({"text": f"Income band {q}: the yearly cost is {band.ratio:.0%} of that band's average yearly income, "
                                    f"so the price is {word}.", "basis": "calculated", "evidence": []})
    if seg.niche:
        out.append({"text": "At this price only the top slice of the highest income band could buy comfortably.",
                    "basis": "calculated", "evidence": []})
    return out[:3]


def llm_input(intake: ProductIntake, aff: Affordability, seg: SegmentScore, view: dict[str, Any],
              anchors: list[dict[str, str]], age_index: dict[str, float], gender_index: dict[str, float]) -> dict[str, Any]:
    return {
        "product": {"name": intake.name, "description": intake.description[:400], "category": intake.category,
                    "features": intake.features[:8], "price": f"{intake.price:g} {intake.currency}",
                    "competitors": intake.competitors[:6], "location": intake.location},
        "affordability": {"tier": aff.tier, "yearly_cost_vs_average_income": round(aff.ratio, 4),
                          "market_position_vs_competitors": (aff.market_position or {}).get("position")},
        "segment": {"id": seg.id, "label": seg.label, "description": seg.description, "ages": list(seg.ages),
                    "reach": {f"band_{q}": r for q, r in seg.reach.items()},
                    "rule_score": seg.score, "score_components": {k: v["value"] for k, v in seg.components.items()},
                    "product_text_matches": seg.matched_keywords},
        "qloo": view,
        "competitor_audience_skew": {"anchors": [a["name"] for a in anchors],
                                     "age_index": {k: round(v, 2) for k, v in age_index.items()},
                                     "gender_index": {k: round(v, 2) for k, v in gender_index.items()},
                                     "note": "relative indexes; negative = under-indexes; not shares"} if age_index or gender_index else None,
    }


def _clean_claims(rows: Any, valid: set[str], allowed_basis: tuple[str, ...], default: str,
                  names: dict[str, list[str]] | None = None, intake: ProductIntake | None = None,
                  dropped: dict[str, int] | None = None, key: str = "") -> tuple[list[dict[str, Any]], int]:
    kept, fixed = [], 0
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or not (r.get("text") or r.get("angle")):
            continue
        text = f"{r.get('angle', '')} {r.get('text', '')}"
        verify: list[str] = []
        if intake is not None:
            drop, verify = screen_claim(text, intake)
            if drop:
                if dropped is not None:
                    dropped[key] = dropped.get(key, 0) + 1
                continue
        ids = [i for i in (r.get("evidence") or []) if i in valid]
        if names is not None and ids:
            # a citation must be traceable: the text has to mention something the cited evidence actually returned
            ids = [i for i in ids if any(_norm(n) and _norm(n) in _norm(text) for n in names.get(i, []))]
        basis = r.get("basis") if r.get("basis") in allowed_basis else default
        if r.get("basis") not in allowed_basis and r.get("basis") in ("evidence", "calculated"):
            fixed += 1  # the model claimed a stronger basis than this field may carry
        if basis == "evidence" and not ids:
            basis, fixed = "interpretation", fixed + 1
        r["evidence"], r["basis"] = ids, basis
        if verify and key == "messages":
            r["verify_product_supports"] = verify
        kept.append(r)
    return kept, fixed


def validate_persona(p: dict[str, Any], seg: SegmentScore, ev_items: list[dict[str, Any]], aff: Affordability,
                     intake: ProductIntake | None = None) -> dict[str, Any]:
    valid = {i["id"] for i in ev_items if i.get("ok")}
    dropped = {"tastes": 0, "where_to_reach": 0}
    downgraded = 0
    nbi = names_by_id(ev_items)
    p["segment_id"] = seg.id
    p["name"] = str(p.get("name") or seg.label)[:80]
    p["headline"] = str(p.get("headline") or seg.description)[:200]
    p["who"] = str(p.get("who") or seg.description)[:400]
    for key, allowed, default in (("motivations", ("evidence", "interpretation"), "interpretation"),
                                  ("messages", ("interpretation",), "interpretation"),
                                  ("objections", ("interpretation",), "interpretation")):
        p[key], f = _clean_claims(p.get(key), valid, allowed, default, nbi, intake, dropped, key)
        downgraded += f
        p[key] = p[key][:3]
    # computed price barriers always lead the objections
    barriers = price_barriers(seg, aff)
    seen = {_norm(o["text"]) for o in barriers}
    p["objections"] = (barriers + [o for o in p["objections"] if _norm(o.get("text", "")) not in seen])[:4]
    p["platforms"] = [{"platform": str(x.get("platform")), "why": str(x.get("why", "")), "basis": "interpretation"}
                      for x in (p.get("platforms") or []) if isinstance(x, dict) and x.get("platform")][:3]
    p["events"] = [{"idea": str(x.get("idea")), "why": str(x.get("why", "")), "basis": "interpretation"}
                   for x in (p.get("events") or []) if isinstance(x, dict) and x.get("idea")][:2]
    places = {_norm(n): n for n in place_names(ev_items, seg.label)}
    aff_by_place = place_affinity(ev_items, seg.label)
    ents = {_norm(n): (n, eid) for n, eid in entity_names(ev_items, seg.label).items()}
    keep_places = []
    for x in p.get("where_to_reach") or []:
        key = _norm(str(x.get("place", "") if isinstance(x, dict) else ""))
        if key in places:
            eid = next((e for n, e in entity_names(ev_items, seg.label).items() if _norm(n) == key), None)
            keep_places.append({"place": places[key],
                                "affinity": round(aff_by_place[places[key]], 2) if places[key] in aff_by_place else None,
                                "evidence": [eid] if eid else [], "basis": "evidence"})
        else:
            dropped["where_to_reach"] += 1
    p["where_to_reach"] = keep_places[:4]
    keep_tastes = []
    for x in p.get("tastes") or []:
        key = _norm(str(x.get("name", "") if isinstance(x, dict) else ""))
        if key in ents:
            n, eid = ents[key]
            keep_tastes.append({"name": n, "kind": str(x.get("kind", "")), "evidence": [eid], "basis": "evidence"})
        else:
            dropped["tastes"] += 1
    p["tastes"] = keep_tastes[:6]
    p["caveats"] = [str(c) for c in (p.get("caveats") or [])][:4]
    p["validation"] = {"dropped": dropped, "downgraded_to_interpretation": downgraded}
    return p


def template_persona(seg: SegmentScore, view: dict[str, Any], aff: Affordability) -> dict[str, Any]:
    """No-LLM persona: only what the rules, the numbers and Qloo returned. No messages, platforms or motivations."""
    tastes = []
    for kind, block in (view.get("lists") or {}).items():
        if kind == "place":
            continue
        for it in block["items"][:2]:
            tastes.append({"name": it["name"], "kind": kind, "evidence": [block["evidence_id"]], "basis": "evidence"})
    places = []
    pl = (view.get("lists") or {}).get("place")
    if pl:
        for it in pl["items"][:3]:
            places.append({"place": it["name"], "affinity": it.get("affinity"),
                           "evidence": [pl["evidence_id"]], "basis": "evidence"})
    return {"segment_id": seg.id, "name": seg.label, "headline": seg.description,
            "who": f"Ages {', '.join(seg.ages)} (rule-based segment).", "motivations": [], "messages": [],
            "objections": price_barriers(seg, aff), "platforms": [], "events": [], "tastes": tastes[:6],
            "where_to_reach": places, "caveats": ["Template persona: no LLM was used, so there are no messages, platforms or motivations."],
            "validation": {"dropped": {}, "downgraded_to_interpretation": 0}}


async def write_personas(llm: LLMClient | None, intake: ProductIntake, aff: Affordability, ranked: list[SegmentScore],
                         bundle: dict[str, Any], delay: float = 0.0) -> list[dict[str, Any]]:
    items = bundle["evidence"]
    out: list[dict[str, Any]] = []
    for n, seg in enumerate(ranked):
        view = segment_view(items, seg)
        persona: dict[str, Any] | None = None
        source, error = "template", None
        if llm:
            if n and delay:
                await asyncio.sleep(delay)
            payload = llm_input(intake, aff, seg, view, bundle["anchors"], bundle["age_index"], bundle["gender_index"])
            try:
                raw = await llm.chat_json(f"persona_{seg.id}", PERSONA_SYSTEM, json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                                          max_tokens=3000)
                if isinstance(raw, dict):
                    persona, source = validate_persona(raw, seg, items, aff, intake), "llm"
                else:
                    error = "LLM returned a non-object"
            except LLMError as e:
                error = str(e)
        if persona is None:
            persona = template_persona(seg, view, aff)
            if error:
                persona["caveats"].append(f"LLM failed for this persona ({error}); template used.")
        persona["source"] = source
        persona["rank"] = n + 1
        persona["score"] = seg.score
        persona["confidence"] = seg.confidence
        persona["score_components"] = {k: v["value"] for k, v in seg.components.items()}
        persona["ages"] = list(seg.ages)
        persona["tied"] = seg.tied
        persona["niche"] = seg.niche
        out.append(persona)
    return out


_LABEL = {"evidence": "Qloo", "calculated": "calculated", "interpretation": "LLM interpretation"}


def markdown(intake: ProductIntake, aff: Affordability, personas: list[dict[str, Any]], bundle: dict[str, Any],
             scoring_notes: list[str], attribution: list[str], synthetic: bool = False) -> str:
    L = [f"# Personas for {intake.name}", ""]
    if synthetic:
        L += ["> **SYNTHETIC DATA**: produced with --mock, not by Qloo.", ""]
    L += [f"**Market:** {aff.country_name} · **Price:** {intake.price:,.2f} {intake.currency} · **Affordability tier:** `{aff.tier}` "
          f"(yearly cost = {aff.ratio:.2%} of average annual income) *(calculated)*", ""]
    for a in bundle.get("anchors", []):
        if a.get("matched_by") == "prefix":
            L += [f"> Competitor '{a['query']}' was matched to Qloo's '{a['name']}'.", ""]
    if bundle.get("anchors"):
        how = {"given": "you listed it", "qloo_tag": "Qloo brands for the product's tag", "llm_confirmed": "suggested by the LLM, confirmed in Qloo",
               "qloo_category": "a Qloo brand in the same category as your competitors", "related": "related to the listed brands in Qloo and in the same Qloo brand category"}
        L += ["**Competitors used** (how each was found):", ""]
        L += [f"- {a['name']} — {how.get(a.get('source', 'given'), a.get('source'))}" for a in bundle["anchors"]] + [""]
        if bundle.get("category"):
            c = bundle["category"]
            L += [f"Category used to find peers: `{c['id'].replace('urn:tag:genre:brand:', '')}` ({'in ' + intake.location if c['scope'] == 'local' else 'worldwide: nothing local'}).", ""]
        if any(a.get("source", "given") != "given" for a in bundle["anchors"]):
            L += ["> Some competitors were found by the tool, not listed by you. Check they are real peers; if not, list your own "
                  "competitors and the audience skew below will be based on them.", ""]
    if bundle.get("age_index"):
        sk = skew_summary(bundle["age_index"], bundle.get("gender_index") or {})
        idx = ", ".join(f"{k} {v:+.2f}" for k, v in bundle["age_index"].items())
        L += [f"**Competitor audience age skew** ({', '.join(a['name'] for a in bundle['anchors'])}; Qloo relative index, "
              f"not shares): {idx}", f"> {sk}", ""]
    elif intake.competitors:
        L += ["**Competitor audience skew:** unavailable (no competitor resolved in Qloo).", ""]
    for p in personas:
        flags = (" · *tied*" if p.get("tied") else "") + (" · *niche at this price*" if p.get("niche") else "")
        L += [f"## {p['rank']}. {p['name']} — {p['headline']}", "",
              f"Segment `{p['segment_id']}` · ages {', '.join(p['ages'])} · score {p['score']:.2f} (ordering aid) · "
              f"confidence {p['confidence']} · written by {p['source']}{flags}", "",
              "Score parts: " + ", ".join(f"{k.replace('_', ' ')} {v:.2f}" for k, v in p["score_components"].items()) + ".", "",
              p["who"], ""]

        def section(title: str, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
            if not rows:
                return
            L.append(f"**{title}**")
            for r in rows:
                txt = " — ".join(str(r[f]) for f in fields if r.get(f))
                tag = _LABEL.get(r.get("basis", "interpretation"), "LLM interpretation")
                warn = f" ⚠ check the product really supports: {', '.join(r['verify_product_supports'])}" if r.get("verify_product_supports") else ""
                cite = warn + (f" {'inspired by ' if r.get('basis') == 'interpretation' else ''}`{','.join(r['evidence'])}`"
                        if r.get("evidence") else "")
                L.append(f"- {txt} *[{tag}]*{cite}")
            L.append("")
        section("Motivations", p["motivations"], ("text",))
        section("Price and other objections", p["objections"], ("text",))
        section("Message ideas (model's marketing ideas; cited tastes only inspired them)", p["messages"], ("angle", "text"))
        section("Tastes (what Qloo returned for this age group here)", p["tastes"], ("name", "kind"))
        if p["where_to_reach"]:
            L.append("**Where to reach them** (places Qloo returned for this age group in this location)")
            for w in p["where_to_reach"]:
                aff_txt = f", affinity {w['affinity']}" if w.get("affinity") is not None else ""
                L.append(f"- {w['place']} *[Qloo{aff_txt}]* `{','.join(w['evidence'])}`")
            L.append("")
        section("Platforms (no platform data in Qloo)", p["platforms"], ("platform", "why"))
        section("Event ideas (no event data in Qloo)", p["events"], ("idea", "why"))
        if p["caveats"]:
            L += ["**Caveats:** " + " ".join(p["caveats"]), ""]
    L += ["## Limits of this report", "",
          "- Income comes from national averages (World Bank), not from the city or from your customers.",
          "- Qloo scores and indexes are relative rankings without sample sizes; none of them is a share of buyers.",
          "- Segments are rule-based assumptions; the score only orders them.",
          "- Platforms and events are the model's interpretation: Qloo has no data on them.",
          "- Evidence ids (E###) refer to `03_evidence.json` in the run folder."]
    L += [f"- {n}" for n in scoring_notes]
    if bundle.get("unresolved"):
        L.append(f"- Not found in Qloo, so not used as signals: {', '.join(bundle['unresolved'])}.")
    L += ["", "## Sources", ""] + [f"- {a}" for a in attribution] + ["- Qloo Taste AI (audience, taste and place signals)"]
    return "\n".join(L) + "\n"
