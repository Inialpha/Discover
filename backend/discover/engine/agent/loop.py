"""The agent loop. The LLM decides its own goals and which tool to call next; code supplies tools, a step budget, a
rolling notebook (so the prompt stays small), and a final check that every cited call and entity id really exists."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from ..personas.intake import ProductIntake
from .tools import Toolbox, clip

AGE_BANDS = {"24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"}
MIN_GOOD_CALLS = 4
MIN_COMPETITORS = 2
MAX_REFUSALS = 3
RATE_LIMIT_WAIT = 30.0

FIELD_GUIDE = """You are a market-research agent. You explore the Qloo taste/culture API with tools to learn who buys a product and which brands compete with it. You decide your own goals and next step.

Call qloo_help(topic) (free) whenever you are unsure about a parameter, filter, signal, tag namespace or the best sequence: topics overview, kinds, filters, signals, weights, demographics, tags, response, pitfalls, recipes. Read 'recipes' first.

Key rules (details and VERIFIED/DOCUMENTED tags are in qloo_help): filter_tags is a HARD category filter, interest_tags/interest_entities only bias ranking; filter_tags + interest_entities ranks category brands by similarity to an anchor; brand records list competitor_brand / customer_segment / industry tags; search is semantic and can return the wrong entity, so read tags; brand location is a soft signal; Qloo has no income, platform or event data.

How to start (the product itself is the business's own, usually new, product: it is NOT in Qloo, so never search for its name):
1. Work out what kind of product it is and which Qloo category tag fits (find_tags, then read the ids).
2. Take the competitors the business gave you (if any) and resolve them with search_entity; check the result's tags and read entity_record.
3. If a search returns the wrong kind of entity, retry with a more specific query (add the product word or the maker's name) or move on to the category route.
4. Get category brands with insights(filter_tags=[category tag], interest_entities=[a verified anchor]); read their records for competitor_brand / customer_segment tags.
5. Ask for audience demographics and tastes of the verified competitors.
The "known" field lists every entity id and tag id you have seen: copy ids from there. Arguments must be LITERAL values copied from earlier results (ids, tag ids). Never write templates such as "{{Q03.tag_ids[0]}}": they are rejected. Use only the argument names listed for each tool. Never finish before you have made real calls, and never claim a search returned something it did not.

Loop: every turn reply with ONE JSON object:
{"goal": "what I am trying to learn now", "notebook": "<=700 chars of what I know and what is left", "action": {"tool": "...", "args": {...}}}
or, when done or out of budget:
{"finish": {"competitors": [{"name": "", "entity_id": "", "why": "", "cites": ["Q03"]}],
            "category": {"tag": "", "why": "", "cites": []},
            "findings": [{"claim": "", "cites": ["Q05"]}],
            "audience_hints": [{"label": "", "ages": [], "claim": "", "cites": []}],
            "gaps": ["what I could not establish"]}}
Rules: only list a competitor if its entity_id appeared in a tool result, it is the right kind of business, and it competes with the product. Every claim cites call ids (Q01...). Say what you could not establish in gaps. Never state facts that no call returned."""


def _context(intake: ProductIntake, aff: dict[str, Any] | None) -> dict[str, Any]:
    c: dict[str, Any] = {"product": intake.name, "what_it_is": intake.product_type or intake.category, "description": intake.description[:300],
                         "price": f"{intake.price:g} {intake.currency}", "purchase_type": intake.purchase_type, "location": intake.location,
                         "competitors_given_by_business": intake.competitors, "features": intake.features[:8]}
    if aff:
        c["affordability"] = aff
    return c


def _recent(toolbox: Toolbox, n: int = 10) -> list[dict[str, Any]]:
    return [{"id": e["id"], "tool": e["tool"], "args": _short_args(e["args"]), "ok": e["ok"], **({"error": str(e["error"])[:120]} if not e["ok"] else {})}
            for e in toolbox.ledger.entries[-n:]]


def _known(toolbox: Toolbox, n_ent: int = 14, n_tags: int = 10) -> dict[str, Any]:
    """Code-kept working memory so a small model never has to scroll back for an id: recent entities and tag ids seen."""
    ents = list(toolbox.ledger.seen_entities.items())[-n_ent:]
    return {"entities_seen": [{"id": eid, "name": v["name"], "from": v["call"]} for eid, v in ents],
            "tag_ids_seen": [t[len("urn:tag:"):] for t in list(toolbox.ledger.seen_tags)[-n_tags:]]}


def next_step_hint(toolbox: Toolbox, intake: ProductIntake) -> str:
    """A concrete suggestion computed from what the agent has (not) done, used when it tries to finish too early.
    The agent still chooses; this only stops a small model from quitting before the useful calls."""
    led = toolbox.ledger
    done = {(e["tool"], json.dumps(e["args"], sort_keys=True, default=str)) for e in led.entries}
    used = [e for e in led.entries if e["ok"]]
    recorded = {str(e["args"].get("entity_id")) for e in used if e["tool"] == "entity_record"}
    has_cat = any(e["tool"] == "find_tags" and (e["observation"] or {}).get("tags") for e in used)
    if not has_cat:
        return f"Call find_tags with query='{intake.product_type or intake.category}' and namespace='genre:brand' to get the category tag."
    todo = [(eid, v["name"]) for eid, v in led.seen_entities.items() if eid not in recorded]
    if not recorded and todo:
        eid, nm = todo[-1]
        return f"Call entity_record on a competitor you found (e.g. {nm}, entity_id {eid}) and read its competitor_brand / similar_brand tags."
    names: list[str] = []
    searched = {str(e["args"].get("query", "")).lower() for e in used if e["tool"] == "search_entity"}
    for e in used:
        if e["tool"] == "entity_record":
            for k in ("competitor_brand", "similar_brand"):
                names += [n for n in ((e["observation"] or {}).get("tags") or {}).get(k, []) if n.lower() not in searched]
    if names:
        return f"Call search_entity for each competitor name Qloo listed on the record: {names[:4]}. Then check their tags."
    anchors = [eid for eid in recorded]
    if anchors and not any(e["tool"] == "insights" for e in used):
        return f"Call insights(kind='brand', filter_tags=[the category tag from find_tags], interest_entities=['{anchors[0]}']) to get category peers ranked by similarity."
    return "Call audience_demographics(entity_ids=[ids of the verified competitors]) so the audience can be described, then finish."


def _short_args(a: Any) -> Any:
    s = json.dumps(a, ensure_ascii=False)
    return a if len(s) < 160 else s[:157] + "..."


def validate_finish(fin: dict[str, Any], toolbox: Toolbox) -> dict[str, Any]:
    """Keep only what the calls support. Everything dropped is reported, never silently lost."""
    ids, seen = toolbox.ledger.ids(), toolbox.ledger.seen_entities
    rejected: list[str] = []

    def cites_ok(items: Any) -> list[str]:
        return [c for c in (items or []) if isinstance(c, str) and c in ids]

    comps, taken = [], set()
    for c in fin.get("competitors") or []:
        if not isinstance(c, dict):
            continue
        eid, name = str(c.get("entity_id") or ""), str(c.get("name") or "")
        if eid not in seen:  # the model often drops or garbles the id: accept an exact name that a call returned (unique)
            by_name = [k for k, v in seen.items() if str(v.get("name") or "").lower() == name.lower()]
            if len(by_name) == 1:
                eid = by_name[0]
        if eid not in seen:
            rejected.append(f"competitor '{name}': entity id was never returned by a Qloo call")
            continue
        if eid in taken:
            continue
        cites = cites_ok(c.get("cites")) or [seen[eid]["call"]]  # the call that returned this entity is its evidence
        taken.add(eid)
        comps.append({"name": seen[eid]["name"] or name, "entity_id": eid, "why": str(c.get("why") or "")[:200], "cites": cites})
    findings = []
    for f in fin.get("findings") or []:
        cites = cites_ok(f.get("cites")) if isinstance(f, dict) else []
        if cites:
            findings.append({"claim": str(f["claim"])[:300], "cites": cites})
        else:
            rejected.append(f"finding without a valid cited call: {str(f)[:80]}")
    hints = []
    for h in fin.get("audience_hints") or []:
        cites = cites_ok(h.get("cites")) if isinstance(h, dict) else []
        if cites:
            hints.append({"label": str(h.get("label"))[:60], "ages": [a for a in h.get("ages") or [] if isinstance(a, str) and a in AGE_BANDS],
                          "claim": str(h.get("claim"))[:300], "cites": cites})
        else:
            rejected.append(f"audience hint without a valid cited call: {str(h)[:80]}")
    cat = fin.get("category") if isinstance(fin.get("category"), dict) else None
    if cat:
        cat = {"tag": str(cat.get("tag"))[:120], "why": str(cat.get("why"))[:200], "cites": cites_ok(cat.get("cites"))}
        if not cat["cites"] or not cat["tag"]:
            rejected.append("category without a valid cited call")
            cat = None
    return {"competitors": comps, "category": cat, "findings": findings, "audience_hints": hints,
            "gaps": [str(g)[:200] for g in fin.get("gaps") or []][:8], "rejected": rejected}


async def run_agent(llm: Any, toolbox: Toolbox, intake: ProductIntake, aff: dict[str, Any] | None = None, max_steps: int = 14,
                    delay: float = 0.0, sleep: Any = asyncio.sleep, on_step: Any = None) -> dict[str, Any]:
    ctx = _context(intake, aff)

    class _Trace(list):
        def append(self, item):  # report each step as it happens
            super().append(item)
            if on_step:
                try:
                    on_step(item)
                except Exception:
                    pass
    catalogue = toolbox.catalogue()
    notebook, last_obs, trace, final = "", None, _Trace(), None
    repeats: dict[str, int] = {}
    refusals = 0
    for step in range(1, max_steps + 1):
        left = max_steps - step
        user = json.dumps({"task": "Find the real competitors of this kind of product in Qloo and who buys this kind of product in this location. The product itself is not in Qloo.",
                           "context": ctx, "tools": catalogue if step == 1 else [t["tool"] for t in catalogue],
                           "steps_left_including_this": left + 1, "notebook": notebook, "known": _known(toolbox), "recent_calls": _recent(toolbox),
                           "last_result": last_obs}, ensure_ascii=False)
        if step > 1 and step % 4 == 0:
            user = user.replace('"tools": [', '"tools_full": ' + json.dumps(catalogue, ensure_ascii=False) + ', "tools": [', 1)
        if left == 0:
            user = user[:-1] + ', "instruction": "LAST STEP: you must finish now."}'
        turn = None
        for attempt in range(3):
            try:
                turn = await llm.chat_json(f"agent_step_{step:02d}", FIELD_GUIDE, user, temperature=0.2, max_tokens=900)
                break
            except Exception as exc:
                if "daily token limit" in str(exc):
                    trace.append({"step": step, "error": f"LLM failed: {exc}"})
                    break
                if attempt < 2 and ("429" in str(exc) or "unparseable" in str(exc) or "no JSON" in str(exc)):
                    if "429" in str(exc):  # token-per-minute limit: wait it out instead of ending the exploration
                        await sleep(RATE_LIMIT_WAIT)
                    continue
                trace.append({"step": step, "error": f"LLM failed: {exc}"})
                break
        if turn is None:  # LLM failure ends exploration; what was found so far is still reported
            break
        if not isinstance(turn, dict):
            trace.append({"step": step, "error": "reply was not a JSON object"})
            last_obs = {"error": "reply must be one JSON object"}
            continue
        notebook = str(turn.get("notebook") or notebook)[:900]
        if isinstance(turn.get("finish"), dict):
            good = sum(1 for e in toolbox.ledger.entries if e["ok"] and e["tool"] != "qloo_help")  # help is free: not exploration
            verified = len(validate_finish(turn["finish"], toolbox)["competitors"])
            too_few = good < MIN_GOOD_CALLS or (verified < MIN_COMPETITORS and refusals < MAX_REFUSALS)
            if too_few and left > 0:
                refusals += 1
                trace.append({"step": step, "goal": turn.get("goal"), "refused_finish": True})
                last_obs = {"error": f"you cannot finish yet: {good} successful Qloo calls and {verified} verified competitors "
                                     f"(need {MIN_COMPETITORS}). Suggested next step: {next_step_hint(toolbox, intake)}"}
                continue
            final = turn["finish"]
            trace.append({"step": step, "goal": turn.get("goal"), "finish": True})
            break
        act = turn.get("action") if isinstance(turn.get("action"), dict) else {}
        tool, args = str(act.get("tool") or ""), act.get("args") if isinstance(act.get("args"), dict) else {}
        obs = await toolbox.run(tool, args)
        sig = json.dumps([tool, args], sort_keys=True, default=str)
        if not obs.get("ok"):
            repeats[sig] = repeats.get(sig, 0) + 1
            if repeats[sig] > 1:
                obs["error"] = str(obs.get("error")) + " | You already made this exact failing call. Change the arguments or the approach."
        trace.append({"step": step, "goal": turn.get("goal"), "tool": tool, "args": args, "call": obs.get("call"), "ok": obs.get("ok")})
        last_obs = clip(obs)
        if delay:
            await sleep(delay)
    if final is None:
        final = {"gaps": ["The agent ran out of steps or failed before it finished; only the calls made are reported."]}
    checked = validate_finish(final, toolbox)
    return {"result": checked, "trace": list(trace), "ledger": toolbox.ledger.entries, "notebook": notebook, "steps": len(trace)}
