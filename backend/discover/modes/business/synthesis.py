"""Evidence -> report. LLM synthesis with claim validation, or a deterministic template when no LLM."""

from __future__ import annotations

import json
import re
from typing import Any

from ...llm.client import LLMClient, LLMError
from . import prompts
from .brief import Brief


def _r(v: Any, n: int = 2) -> Any:
    return round(v, n) if isinstance(v, float) else v


def _compact_entity(e: dict[str, Any], tags_n: int) -> dict[str, Any]:
    out = {"name": e.get("name"), "affinity": _r(e.get("affinity"))}
    if e.get("disambiguation"):
        out["info"] = str(e["disambiguation"])[:60]
    if tags_n and e.get("tags"):
        out["tags"] = [t.get("name") for t in e["tags"][:tags_n] if t.get("name")]
    imdb = (e.get("external") or {}).get("imdb")
    if imdb and imdb.get("rating") is not None:
        out["imdb"] = imdb.get("rating")
    return out


def compact_evidence(items: list[dict[str, Any]], per_list: int = 6, tags_n: int = 3) -> list[dict[str, Any]]:
    """Small, LLM-friendly view of the evidence (full data stays in 03_evidence.json)."""
    out = []
    for it in items:
        row: dict[str, Any] = {k: it.get(k) for k in ("id", "step", "label") if it.get(k)}
        if not it.get("ok"):
            row["error"] = it.get("error")
            out.append(row)
            continue
        d = it.get("data") or {}
        if it["step"] == "resolve":
            ch = d.get("chosen")
            row["resolved"] = (ch or {}).get("name") if ch else None
        elif it["step"] == "taste":
            row["tags"] = [{"name": t.get("name"), "affinity": _r(t.get("affinity"))} for t in d.get("tags", [])[:per_list + 4]]
        elif it["step"] == "affinity":
            row["kind"] = d.get("kind")
            row["top"] = [_compact_entity(e, tags_n) for e in d.get("entities", [])[:per_list]]
        elif it["step"] == "demographics":
            row["scores"] = {g: {k: _r(v) for k, v in vals.items()} for g, vals in d.get("groups", {}).items()}
        elif it["step"] == "heatmap":
            pts = d.get("points", [])[:min(per_list, 5)]
            row["areas"] = [{"geohash": p.get("geohash"), "lat": _r(p.get("lat"), 3), "lon": _r(p.get("lon"), 3),
                             "affinity": _r(p.get("affinity")), "demo_affinity": _r(p.get("demographics_affinity")),
                             "near": [f"{n['name']} ({n['km']}km)" for n in p.get("nearby_places", [])[:1]]} for p in pts]
        elif it["step"] == "compare":
            row["shared_tags_by_similarity"] = [{"name": t.get("name"), "score": _r(t.get("score"))} for t in d.get("tags", [])[:per_list + 2]]
        if it.get("segment"):
            row["segment"] = it["segment"]
        out.append(row)
    return out


def fit_evidence(items: list[dict[str, Any]], budget_chars: int) -> tuple[list[dict[str, Any]], str]:
    """Shrink the evidence view until its JSON fits the budget (provider token limits are often small)."""
    for per_list, tags_n in ((6, 3), (5, 2), (4, 1), (3, 0), (2, 0), (1, 0)):
        view = compact_evidence(items, per_list, tags_n)
        text = json.dumps(view, ensure_ascii=False, separators=(",", ":"))
        if len(text) <= budget_chars:
            return view, text
    return view, text[:budget_chars]


def _ids(items: list[dict[str, Any]]) -> set[str]:
    return {i["id"] for i in items}


def validate_report(report: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    valid = _ids(items)
    dropped = capped = 0
    for f in report.get("findings") or []:
        if f.get("confidence") not in ("medium", "low"):  # relative scores, no sample sizes: never claim 'high'
            f["confidence"] = "medium"
            capped += 1
    if capped:
        report.setdefault("caveats", []).append("Confidence is capped at 'medium': Qloo scores are relative rankings without sample sizes.")
    for key in ("findings", "media_recommendations", "messaging_angles"):
        kept = []
        for row in report.get(key) or []:
            ids = [i for i in (row.get("evidence_ids") or []) if i in valid]
            if key == "findings" and not ids:
                dropped += 1
                continue
            row["evidence_ids"] = ids
            if key == "media_recommendations" and row.get("basis") not in ("qloo", "interpretation"):
                row["basis"] = "qloo" if ids else "interpretation"
            if key != "findings" and not ids:
                row["unsupported"] = True
            kept.append(row)
        report[key] = kept
    if dropped:
        report.setdefault("caveats", []).append(f"{dropped} finding(s) removed: they cited no valid evidence.")
    return report


def template_report(brief: Brief, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic, no-LLM report: lists what the API returned, with no interpretation."""
    findings, media = [], []
    for it in items:
        d = it.get("data") or {}
        if not it.get("ok"):
            continue
        if it["step"] == "affinity" and d.get("entities"):
            top = d["entities"][:3]
            names = ", ".join(f"{e['name']} (affinity {e['affinity']})" if e.get("affinity") is not None else str(e["name"]) for e in top)
            findings.append({"claim": f"{it['segment']} — top-ranked {d['kind']} (API order): {names}", "evidence_ids": [it["id"]], "confidence": "medium"})
            if d["kind"] in ("movie", "tv_show", "artist", "podcast"):
                media.append({"channel_or_title": top[0]["name"], "why": f"top-ranked {d['kind']} returned for {it['segment']}", "evidence_ids": [it["id"]]})
        elif it["step"] == "taste" and d.get("tags"):
            names = ", ".join(str(t["name"]) for t in d["tags"][:5])
            findings.append({"claim": f"{it['segment']} — leading taste tags: {names}", "evidence_ids": [it["id"]], "confidence": "medium"})
        elif it["step"] == "heatmap" and d.get("points"):
            findings.append({"claim": f"{it['segment']} — {len(d['points'])} heatmap areas returned in {brief.location}", "evidence_ids": [it["id"]], "confidence": "low"})
    failed = [i for i in items if not i.get("ok")]
    return {
        "headline": f"Raw findings for: {brief.question}",
        "audience_profile": "Not interpreted (no LLM configured). See findings.",
        "findings": findings, "media_recommendations": media, "messaging_angles": [],
        "location_notes": None,
        "caveats": ["Template report: no LLM synthesis was used.",
                    *([f"{len(failed)} Qloo call(s) failed or were skipped; see 03_evidence.json."] if failed else [])],
        "next_steps": [],
    }


async def synthesize(llm: LLMClient | None, brief: Brief, items: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    if llm is None:
        return validate_report(template_report(brief, items), items), "template"
    budget = llm.s.llm_max_input_chars
    _, ev_text = fit_evidence(items, budget)
    brief_view = {"goal": brief.goal, "product": brief.product, "own_brand": brief.own_brand, "competitors": brief.competitors,
                  "location": brief.location, "segments": [s.label for s in brief.segments]}
    user = json.dumps({"question": brief.question, "brief": brief_view}, ensure_ascii=False) + "\nEVIDENCE:" + ev_text
    try:
        report = await llm.chat_json("synthesis", prompts.SYNTH_SYSTEM, user, max_tokens=llm.s.llm_max_output_tokens)
        if not isinstance(report, dict):
            raise LLMError("synthesis was not an object")
        return validate_report(report, items), "llm"
    except LLMError as exc:
        rep = template_report(brief, items)
        rep["caveats"].append(f"LLM synthesis failed ({exc}); template used.")
        return validate_report(rep, items), "template-fallback"


def to_markdown(brief: Brief, report: dict[str, Any], items: list[dict[str, Any]], mode: str, resolved: Any = None) -> str:
    L: list[str] = [f"# {report.get('headline') or brief.question}", "", f"> **Question:** {brief.question}",
                    f"> **Report mode:** {mode} · **Location:** {brief.location or '—'} · "
                    f"**Segments:** {', '.join(s.label for s in brief.segments) or '—'}", ""]
    if report.get("audience_profile"):
        L += ["## Audience", "", str(report["audience_profile"]), ""]
    def cite(r): return " ".join(f"`{i}`" for i in r.get("evidence_ids") or [])
    if report.get("findings"):
        L += ["## Findings", ""] + [f"- {f['claim']} _(confidence: {f.get('confidence', '?')})_ {cite(f)}" for f in report["findings"]] + [""]
    if report.get("media_recommendations"):
        L += ["## Media recommendations", ""] + [f"- **{r.get('channel_or_title')}** — {r.get('why')} {cite(r)}{' _(interpretation)_' if r.get('basis') == 'interpretation' else ''}" for r in report["media_recommendations"]] + [""]
    if report.get("messaging_angles"):
        L += ["## Messaging angles (interpretation)", ""] + [f"- **{r.get('angle')}** — {r.get('why')} {cite(r)}" for r in report["messaging_angles"]] + [""]
    if report.get("location_notes"):
        L += ["## Location", "", str(report["location_notes"]), ""]
    if report.get("caveats"):
        L += ["## Caveats", ""] + [f"- {c}" for c in report["caveats"]] + [""]
    if report.get("next_steps"):
        L += ["## Next steps", ""] + [f"- {c}" for c in report["next_steps"]] + [""]
    L += ["## Evidence index", "", "| id | step | label | ok | files |", "|---|---|---|---|---|"]
    for it in items:
        files = ", ".join(it.get("source_files") or [])
        L.append(f"| {it['id']} | {it['step']} | {it['label']} | {'yes' if it['ok'] else 'NO: ' + str(it.get('error'))} | {files} |")
    return "\n".join(L) + "\n"
