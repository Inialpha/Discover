"""Market coverage: (1) a code-built note attached to every report, (2) the `discover coverage` probe that
measures how much a location changes Qloo's answers, so we know which markets are strong before promising anything."""

from __future__ import annotations

import asyncio
import itertools
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


async def probe_coverage(client: QlooClient, locations: list[str], gender: str | None, age: str | None,
                         kinds: list[str], take: int = 10) -> dict[str, Any]:
    lo, hi = parse_age_text(age) if age else (None, None)
    base = calls.Signals(age=age_range_to_buckets(lo, hi), gender=normalize_gender(gender))
    plan: list[tuple[str, str | None, calls.CallSpec]] = []
    for kind in kinds:
        if kind != "place":
            plan.append((kind, None, calls.insights_entities("coverage", f"baseline-{kind}", kind, base, take=take, explain=False)))
    for loc in locations:
        sig = calls.Signals(age=base.age, gender=base.gender, location=loc)
        for kind in kinds:
            plan.append((kind, loc, calls.insights_entities("coverage", f"{loc}-{kind}", kind, sig, take=take, explain=False)))
        plan.append(("heatmap", loc, calls.insights_heatmap("coverage", f"{loc}-heatmap", sig)))
    results = await asyncio.gather(*(client.call(p[2]) for p in plan))

    names: dict[tuple[str, str | None], list[str]] = {}
    heat: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    for (kind, loc, spec), res in zip(plan, results):
        if not res.ok:
            errors.append({"call": spec.label, "error": res.error or res.skipped_reason, "files": res.files})
            continue
        if kind == "heatmap":
            heat[loc or ""] = len(nz.heatmap_from_body(res.body))
        else:
            names[(kind, loc)] = _names(res.body, nz.entities_from_insights)

    table: dict[str, dict[str, Any]] = {}
    for loc in locations:
        row: dict[str, Any] = {"heatmap_areas": heat.get(loc), "kinds": {}}
        influences = []
        for kind in kinds:
            cur = names.get((kind, loc))
            if cur is None:
                row["kinds"][kind] = None
                continue
            entry: dict[str, Any] = {"returned": len(cur), "top3": cur[:3]}
            if kind != "place" and (kind, None) in names:
                entry["overlap_with_no_location"] = jaccard(cur, names[(kind, None)])
                entry["location_influence"] = round(1 - entry["overlap_with_no_location"], 3)
                if kind in MEDIA_KINDS:
                    influences.append(entry["location_influence"])
            row["kinds"][kind] = entry
        if influences:
            m = sum(influences) / len(influences)
            row["avg_location_influence"] = round(m, 3)
            row["grade"] = "strong" if m >= 0.6 else "moderate" if m >= 0.3 else "weak (mostly global)"
        table[loc] = row

    pairwise: dict[str, dict[str, float]] = {}
    for kind in kinds:
        if kind == "place":
            continue
        vals = [jaccard(names[(kind, a)], names[(kind, b)]) for a, b in itertools.combinations(locations, 2)
                if (kind, a) in names and (kind, b) in names]
        if vals:
            pairwise[kind] = {"mean_overlap_between_cities": round(sum(vals) / len(vals), 3)}
    return {"demographic": {"gender": base.gender, "age_buckets": base.age}, "locations": table,
            "between_cities": pairwise, "errors": errors,
            "how_to_read": ("location_influence = 1 - overlap of the top results with and without the location (0 = location "
                            "changed nothing). Grade thresholds (0.3 / 0.6) are heuristics, not Qloo facts."),
            "calls_used": client.calls_used}


def coverage_markdown(res: dict[str, Any], synthetic: bool) -> str:
    L = ["# Market coverage probe", ""]
    if synthetic:
        L += ["> **SYNTHETIC (--mock): not real Qloo data.**", ""]
    L += [f"Demographic: {res['demographic']}", "", res["how_to_read"], "",
          "| Location | Grade | Avg influence | Heatmap areas | Places |", "|---|---|---|---|---|"]
    for loc, row in res["locations"].items():
        place = (row["kinds"].get("place") or {}).get("returned")
        L.append(f"| {loc} | {row.get('grade', 'n/a')} | {row.get('avg_location_influence', 'n/a')} | {row['heatmap_areas']} | {place} |")
    L += ["", "## Per kind (top 3 results)", ""]
    for loc, row in res["locations"].items():
        L.append(f"### {loc}")
        for kind, e in row["kinds"].items():
            if e:
                L.append(f"- **{kind}**: {', '.join(e['top3'])} _(influence {e.get('location_influence', 'n/a')})_")
        L.append("")
    if res["between_cities"]:
        L += ["## Overlap between cities (1.0 = identical lists)", ""] + [f"- {k}: {v['mean_overlap_between_cities']}" for k, v in res["between_cities"].items()] + [""]
    if res["errors"]:
        L += ["## Errors", ""] + [f"- {e['call']}: {e['error']}" for e in res["errors"]]
    return "\n".join(L) + "\n"
