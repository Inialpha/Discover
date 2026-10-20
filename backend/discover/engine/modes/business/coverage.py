"""Market coverage: (1) a code-built note attached to every report, (2) the `discover coverage` probe that
measures how much a location changes Qloo's answers, so we know which markets are strong before promising anything."""

from __future__ import annotations

import asyncio
import itertools
import re
from typing import Any

from ...qloo import calls, normalize as nz
from ...qloo.client import QlooClient
from ...qloo.demographics import age_range_to_buckets, normalize_gender, parse_age_text

STANDING_NOTE = (
    "Qloo's coverage varies by market and by media type. Place and heatmap results are tied to the location you "
    "ask about; movie, TV, music, podcast and brand recommendations can reflect global taste for the demographic "
    "even when a city is given. Treat them as taste signals for the audience, not a local chart or sales data."
)
MEDIA_KINDS = ("movie", "tv_show", "artist", "podcast", "brand")


def report_coverage(items: list[dict[str, Any]], locations: list[str]) -> dict[str, Any]:
    per: dict[str, dict[str, int]] = {}
    for it in items:
        if not it.get("ok"):
            continue
        d = it.get("data") or {}
        key = (it.get("segment") or "").split(" @ ")[-1] if " @ " in (it.get("segment") or "") else (locations[0] if locations else "-")
        row = per.setdefault(key, {"places_returned": 0, "heatmap_areas": 0, "heatmap_areas_named": 0})
        if it["step"] == "affinity" and d.get("kind") == "place":
            row["places_returned"] += len(d.get("entities", []))
        if it["step"] == "heatmap":
            pts = d.get("points", [])
            row["heatmap_areas"] += len(pts)
            row["heatmap_areas_named"] += sum(1 for p in pts if p.get("nearby_places"))
    return {"locations": locations, "per_location": per, "note": STANDING_NOTE}


def _names(body: Any, normalizer) -> list[str]:
    return [e["name"] for e in normalizer(body) if e.get("name")]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    return round(len(sa & sb) / len(sa | sb), 3) if (sa or sb) else 0.0


_COUNTRIES = (
    "United States", "United Kingdom", "Nigeria", "Japan", "India", "France", "Germany", "Italy", "Spain", "Brazil",
    "Mexico", "Canada", "Australia", "China", "South Korea", "Korea", "Ghana", "Kenya", "South Africa", "Egypt",
    "United Arab Emirates", "Saudi Arabia", "Turkey", "Indonesia", "Thailand", "Singapore", "Argentina", "Colombia",
    "Netherlands", "Sweden", "Portugal", "Ireland", "Russia", "Philippines", "Vietnam", "Pakistan", "Morocco",
)
_ALIASES = {"usa": "united states", "us": "united states", "uk": "united kingdom", "england": "united kingdom",
            "korea": "south korea", "republic of korea": "south korea"}
_US_ADDR = re.compile(r",\s*[A-Z]{2}(?:\s+\d{5})?\s*$")


def _canon(name: str) -> str:
    n = re.sub(r"[^a-z ]", "", name.lower()).strip()
    return _ALIASES.get(n, n)


def infer_country(place_entities: list[dict[str, Any]]) -> str | None:
    """Most common country at the end of the returned places' addresses (heuristic; None if unclear)."""
    votes: dict[str, int] = {}
    for e in place_entities:
        addr = ((e.get("properties") or {}).get("address") or "").strip()
        if not addr:
            continue
        hit = next((c for c in _COUNTRIES if addr.rstrip(" .").lower().endswith(c.lower())), None)
        if not hit and _US_ADDR.search(addr):
            hit = "United States"
        if not hit:
            tail = addr.split(",")[-1].strip()
            hit = tail if tail and re.fullmatch(r"[A-Za-z .'-]{3,40}", tail) else None
        if hit:
            votes[_canon(hit)] = votes.get(_canon(hit), 0) + 1
    return max(votes, key=votes.get) if votes else None


def local_share(kind: str, entities: list[dict[str, Any]], country: str | None) -> float | None:
    """Share of results whose own metadata names the market's country (movies/TV: release_country; brands:
    key_markets). Artists/podcasts carry no such metadata -> None."""
    field = {"movie": "release_country", "tv_show": "release_country", "brand": "key_markets"}.get(kind)
    if not field or not country or not entities:
        return None
    known = hit = 0
    for e in entities:
        vals = (e.get("properties") or {}).get(field)
        if not vals:
            continue
        known += 1
        vals = vals if isinstance(vals, list) else [vals]
        if country in {_canon(str(v)) for v in vals}:
            hit += 1
    return round(hit / known, 2) if known else None


async def probe_coverage(client: QlooClient, locations: list[str], gender: str | None, age: str | None,
                         kinds: list[str], take: int = 10) -> dict[str, Any]:
    lo, hi = parse_age_text(age) if age else (None, None)
    base = calls.Signals(age=age_range_to_buckets(lo, hi), gender=normalize_gender(gender))
    plan: list[tuple[str, str, calls.CallSpec]] = []
    for loc in locations:
        sig = calls.Signals(age=base.age, gender=base.gender, location=loc)
        for kind in kinds:
            plan.append((kind, loc, calls.insights_entities("coverage", f"{loc}-{kind}", kind, sig, take=take, explain=False)))
        plan.append(("heatmap", loc, calls.insights_heatmap("coverage", f"{loc}-heatmap", sig, take=30)))
    results = await asyncio.gather(*(client.call(p[2]) for p in plan))

    ents: dict[tuple[str, str], list[dict[str, Any]]] = {}
    heat: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    for (kind, loc, spec), res in zip(plan, results):
        if not res.ok:
            errors.append({"call": spec.label, "error": res.error or res.skipped_reason, "files": res.files})
            continue
        if kind == "heatmap":
            heat[loc] = len(nz.heatmap_from_body(res.body))
        else:
            # keep compact props (release_country / key_markets / address) for the locality check
            ents[(kind, loc)] = nz.entities_from_insights(res.body)

    table: dict[str, dict[str, Any]] = {}
    for loc in locations:
        country = infer_country(ents.get(("place", loc), []))
        row: dict[str, Any] = {"country_inferred": country, "heatmap_areas": heat.get(loc), "kinds": {}}
        shares = []
        for kind in kinds:
            cur = ents.get((kind, loc))
            if cur is None:
                row["kinds"][kind] = None
                continue
            entry: dict[str, Any] = {"returned": len(cur), "top3": [e["name"] for e in cur[:3] if e.get("name")]}
            ls = local_share(kind, cur, country)
            if ls is not None:
                entry["local_share"] = ls
                shares.append(ls)
            row["kinds"][kind] = entry
        if shares:
            m = sum(shares) / len(shares)
            row["avg_local_share"] = round(m, 2)
            row["grade"] = "strong" if m >= 0.6 else "moderate" if m >= 0.3 else "weak (mostly foreign/global)"
        table[loc] = row

    pairwise: dict[str, dict[str, float]] = {}
    for kind in kinds:
        if kind == "place":
            continue
        vals = [jaccard([e["name"] for e in ents[(kind, a)]], [e["name"] for e in ents[(kind, b)]])
                for a, b in itertools.combinations(locations, 2) if (kind, a) in ents and (kind, b) in ents]
        if vals:
            pairwise[kind] = {"mean_overlap_between_cities": round(sum(vals) / len(vals), 3)}
    return {"demographic": {"gender": base.gender, "age_buckets": base.age}, "locations": table,
            "between_cities": pairwise, "errors": errors,
            "how_to_read": ("local_share = share of returned movies/TV (release_country) and brands (key_markets) whose own metadata names "
                            "the market's country; the country is inferred from the returned places' addresses. Artists and podcasts "
                            "have no such metadata, so they are not graded. Grade thresholds (0.3 / 0.6) are heuristics. For the US/UK, "
                            "'local' cannot be told apart from Qloo's global default, so a high share there is expected, not proof."),
            "calls_used": client.calls_used}


def coverage_markdown(res: dict[str, Any], synthetic: bool) -> str:
    L = ["# Market coverage probe", ""]
    if synthetic:
        L += ["> **SYNTHETIC (--mock): not real Qloo data.**", ""]
    L += [f"Demographic: {res['demographic']}", "", res["how_to_read"], "",
          "| Location | Inferred country | Grade | Avg local share | Heatmap areas returned (take ignored) |", "|---|---|---|---|---|"]
    for loc, row in res["locations"].items():
        L.append(f"| {loc} | {row.get('country_inferred')} | {row.get('grade', 'n/a')} | {row.get('avg_local_share', 'n/a')} | {row['heatmap_areas']} |")
    L += ["", "## Per kind (top 3 results)", ""]
    for loc, row in res["locations"].items():
        L.append(f"### {loc}")
        for kind, e in row["kinds"].items():
            if e:
                L.append(f"- **{kind}**: {', '.join(e['top3'])} _(local share {e.get('local_share', 'n/a')})_")
        L.append("")
    if res["between_cities"]:
        L += ["## Overlap between cities (1.0 = identical lists)", ""] + [f"- {k}: {v['mean_overlap_between_cities']}" for k, v in res["between_cities"].items()] + [""]
    if res["errors"]:
        L += ["## Errors", ""] + [f"- {e['call']}: {e['error']}" for e in res["errors"]]
    return "\n".join(L) + "\n"
