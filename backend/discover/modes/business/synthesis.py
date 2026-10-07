"""Evidence -> report. LLM synthesis with claim validation, or a deterministic template when no LLM."""

from __future__ import annotations

import json
import re
from typing import Any

from ...llm.client import LLMClient, LLMError
from . import prompts
from .brief import Brief


def compact_evidence(items: list[dict[str, Any]], per_list: int = 6) -> list[dict[str, Any]]:
    out = []
    for it in items:
        row = {k: it.get(k) for k in ("id", "step", "label", "segment", "ok", "error")}
        d = it.get("data")
        if isinstance(d, dict):
            d = dict(d)
            for key in ("entities", "tags", "points", "candidates"):
                if isinstance(d.get(key), list):
                    d[key] = [
                        {k: v for k, v in x.items() if k in ("name", "affinity", "popularity", "type", "types", "weight", "geohash", "lat", "lon", "tags", "explainability", "id") and v not in (None, [], {})}
                        for x in d[key][:per_list]
                    ]
        row["data"] = d
        out.append(row)
    return out


def _ids(items: list[dict[str, Any]]) -> set[str]:
    return {i["id"] for i in items}


def validate_report(report: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    valid = _ids(items)
    dropped = 0
    for key in ("findings", "media_recommendations", "messaging_angles"):
        kept = []
        for row in report.get(key) or []:
            ids = [i for i in (row.get("evidence_ids") or []) if i in valid]
            if key == "findings" and not ids:
                dropped += 1
                continue
            row["evidence_ids"] = ids
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
            findings.append({"claim": f"{it['segment']} — top-ranked {d["kind"]} (API order): {names}", "evidence_ids": [it["id"]], "confidence": "medium"})
            if d["kind"] in ("movie", "tv_show", "artist", "podcast"):
                media.append({"channel_or_title": top[0]["name"], "why": f"top-ranked {d["kind"]} returned for {it['segment']}", "evidence_ids": [it["id"]]})
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
    user = json.dumps({"question": brief.question, "brief": brief.to_dict(), "evidence": compact_evidence(items)}, ensure_ascii=False)
    try:
        report = await llm.chat_json("synthesis", prompts.SYNTH_SYSTEM, user, max_tokens=4000)
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
        L += ["## Media recommendations", ""] + [f"- **{r.get('channel_or_title')}** — {r.get('why')} {cite(r)}" for r in report["media_recommendations"]] + [""]
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
