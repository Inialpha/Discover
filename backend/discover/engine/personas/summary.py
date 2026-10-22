"""The plain-language executive summary and report text shown to business readers.

Everything here is assembled from fields the analysis already holds (names, ages, tastes, places, platforms, the price tier and the
audience age skew). No model is called and nothing is added that the analysis did not find. It never mentions evidence ids, scores or tools.
"""

from __future__ import annotations

from typing import Any

PRICE_WORDS = {"budget": "an affordable price", "mass": "a mainstream price", "upper": "an upper-market price", "premium": "a premium price"}
AGE_WORDS = {"24_and_younger": "under 25", "25_to_29": "25 to 29", "30_to_34": "30 to 34", "35_to_44": "35 to 44",
             "45_to_54": "45 to 54", "55_and_older": "55 and over"}
BASIS_WORDS = {"evidence": "Backed by data", "calculated": "From the numbers", "interpretation": "Our suggestion"}


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else (items[0] if items else "")


def _names(rows: list[dict[str, Any]], key: str, n: int) -> list[str]:
    return [str(r[key]) for r in rows if r.get(key)][:n]


def build(intake: dict[str, Any], res: dict[str, Any]) -> dict[str, Any]:
    personas = res.get("personas") or []
    aff = res.get("affordability") or {}
    anchors = [a["name"] for a in (res.get("anchor_audience") or {}).get("anchors") or []]
    age_index = (res.get("anchor_audience") or {}).get("age_index") or {}
    n = len(personas)
    bullets: list[dict[str, str]] = []

    price = f"At {intake['price']:g} {intake['currency']}" + (f" ({aff['local_price']:,.0f} {aff['local_currency']} locally)" if aff.get("local_price") and aff.get("local_currency") != intake["currency"] else "")
    bullets.append({"label": "Your price", "text": f"{price}, {intake['name']} sits at {PRICE_WORDS.get(aff.get('tier'), 'a typical price')} for {aff.get('country_name') or intake['location']}."})
    if age_index and anchors:
        top = [AGE_WORDS.get(k, k) for k, _ in sorted(age_index.items(), key=lambda kv: -kv[1])[:2]]
        bullets.append({"label": "Who buys from competitors", "text": f"Customers of {_join(anchors[:4])} lean towards people aged {_join(top)}."})
    if personas:
        lead = [f"{p['display_name']} ({p['age_label']}): {p['title']}" for p in personas[:3]]
        bullets.append({"label": "Groups to look at first", "text": "; ".join(lead) + "."})
        p = personas[0]
        likes = _names(p.get("tastes") or [], "name", 3)
        if likes:
            bullets.append({"label": f"What {p['display_name']} likes", "text": _join(likes) + "."})
        where = _names(p.get("platforms") or [], "platform", 3)
        places = _names(p.get("where_to_reach") or [], "place", 2)
        if where or places:
            parts = ([f"online on {_join(where)}"] if where else []) + ([f"around {_join(places)} in {intake['location']}"] if places else [])
            bullets.append({"label": f"Where to find {p['display_name']}", "text": " and ".join(parts).capitalize() + "."})
        hurdle = next((o["text"] for o in p.get("objections") or [] if o.get("basis") != "calculated"), None)
        if hurdle:
            bullets.append({"label": "Watch out for", "text": hurdle.rstrip(".") + "."})
    bullets.append({"label": "Next step", "text": "Try the message ideas for each group on the platforms listed, and see which one gets the best response."})
    head = f"{intake['name']} in {intake['location']}: {n} {'group' if n == 1 else 'groups'} of likely buyers" if n else f"{intake['name']} in {intake['location']}"
    return {"headline": head, "bullets": bullets,
            "note": "Items marked “Our suggestion” are ideas to test, not facts about these customers."}


def markdown(intake: dict[str, Any], res: dict[str, Any]) -> str:
    """The downloadable report in plain words."""
    s = res.get("executive_summary") or build(intake, res)
    L = [f"# {intake['name']}: who your customers are", "", f"*{s['headline']}*", "", "## Summary", ""]
    L += [f"- **{b['label']}:** {b['text']}" for b in s["bullets"]] + ["", f"*{s['note']}*", ""]
    for p in res.get("personas") or []:
        L += [f"## {p['rank']}. {p['display_name']}: {p['title']}", "", f"Age {p['age_label']}. {p.get('summary', '')}", ""]

        def sec(title: str, rows: list[dict[str, Any]], *fields: str) -> None:
            rows = [r for r in rows if any(r.get(f) for f in fields)]
            if rows:
                L.append(f"**{title}**")
                L.extend(f"- {' — '.join(str(r[f]) for f in fields if r.get(f))} *({BASIS_WORDS.get(r.get('basis', 'interpretation'))})*" for r in rows)
                L.append("")
        sec("What drives them", p.get("motivations") or [], "text")
        sec("What might stop them", p.get("objections") or [], "text")
        sec("Messages to try", p.get("messages") or [], "angle", "text")
        sec("What they like", [{**t, "name": t["name"]} for t in p.get("tastes") or []], "name")
        sec("Where to find them online", p.get("platforms") or [], "platform")
        sec(f"Places in {intake['location']}", p.get("where_to_reach") or [], "place")
        sec("Event ideas", p.get("events") or [], "idea", "why")
        if p.get("caveats"):
            L += ["**Worth knowing:** " + " ".join(p["caveats"]), ""]
    L += ["## About this report", "",
          "Customer groups are illustrations, not real people; names and pictures are for illustration. "
          "“Backed by data” means taste and market data for your location supports it. “From the numbers” is worked out from your price and public income figures. "
          "“Our suggestion” is our own reasoning from that data: treat it as an idea to test.",
          "", "Taste and market data from Qloo. Income data from the World Bank.", ""]
    return "\n".join(L)
