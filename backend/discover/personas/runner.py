"""`discover personas`: intake -> affordability -> anchor audience skew (Qloo) -> re-rank -> per-persona evidence
(Qloo) -> persona cards (LLM, validated) -> run folder + zip.

Exit codes: 0 ok · 1 partial Qloo/LLM failures · 2 all Qloo calls failed · 3 bad input / missing data / config.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings
from ..llm.client import LLMClient
from ..qloo.client import QlooClient
from ..qloo.mock import make_transport
from ..recorder import RunRecorder, slugify
from . import evidence as E
from . import writer
from .affordability import ReferenceDataMissing, assess
from .fx_note import FX_ATTRIBUTION
from .intake import ProductIntake
from .refdata.store import ReferenceStore
from .scoring import score_segments
from .segments import SEGMENTS


@dataclass
class PersonaOptions:
    intake: ProductIntake
    out: Path = Path("runs")
    kinds: list[str] = field(default_factory=lambda: list(E.DEFAULT_KINDS))
    take: int = 8
    no_llm: bool = False
    mock: bool = False
    dry_run: bool = False
    max_calls: int = 150
    concurrency: int = 2
    delay: float = 0.0
    llm_delay: float = 0.0
    zip: bool = True
    refresh: bool = False
    discover: bool = True  # find competitors through Qloo when fewer than 5 are given
    agent: bool = False  # the LLM explores Qloo with tools instead of the fixed competitor steps
    agent_steps: int = 14


def _agent_competitors(comps: list[dict[str, Any]], intake: ProductIntake, tb: Any) -> list[dict[str, Any]]:
    given = {c.lower() for c in intake.competitors}
    return [{"query": c["name"], "entity_id": c["entity_id"], "name": c["name"], "matched_by": "agent",
             "source": "agent", "tags": [], "why": c["why"], "cites": c["cites"], "listed_by_you": c["name"].lower() in given}
            for c in comps]


async def execute_personas(opts: PersonaOptions, settings: Settings, store: ReferenceStore,
                           llm_transport: httpx.AsyncBaseTransport | None = None,
                           mock_reject: Any = None, qloo_transport: httpx.AsyncBaseTransport | None = None) -> tuple[int, Path, dict[str, Any]]:
    intake = opts.intake
    run_dir = opts.out / f"{datetime.now():%Y%m%d-%H%M%S}_personas_{slugify(intake.name)}"
    rec = RunRecorder(run_dir)
    started = time.time()
    summary: dict[str, Any] = {"run_dir": str(run_dir), "synthetic": opts.mock, "warnings": []}
    rec.write_json("00_input.json", {"intake": intake.to_dict(), "kinds": opts.kinds, "take": opts.take, "mock": opts.mock,
                                     "dry_run": opts.dry_run, "qloo_base_url": settings.qloo_base_url,
                                     "qloo_key_present": bool(settings.qloo_api_key), "llm_model": settings.llm_model,
                                     "llm_configured": settings.llm_configured})
    errs = intake.validate()
    if errs:
        summary.update(status="invalid_intake", errors=errs)
        rec.write_json("99_run_summary.json", summary)
        return 3, run_dir, summary

    if opts.refresh and intake.market:
        rep = store.refresh([intake.market.iso3], [intake.market.currency, intake.currency])
        summary["refresh"] = {"fetched": rep["fetched"], "failed": rep["failed"], "empty": rep["empty"]}
    try:
        aff = assess(intake, store)
    except ReferenceDataMissing as e:
        summary.update(status="missing_reference_data", errors=[str(e)])
        rec.write_json("99_run_summary.json", summary)
        return 3, run_dir, summary

    if not (settings.qloo_api_key or opts.mock or opts.dry_run):
        summary.update(status="no_qloo_key")
        summary["warnings"].append("QLOO_API_KEY missing. Use --mock or --dry-run, or set the key.")
        rec.write_json("99_run_summary.json", summary)
        return 3, run_dir, summary

    llm: LLMClient | None = None
    # --mock means "no real services": the LLM is skipped too unless a transport is injected (tests)
    if settings.llm_configured and not opts.no_llm and not opts.dry_run and (not opts.mock or llm_transport is not None):
        llm = LLMClient(settings, rec, transport=llm_transport)
    elif not (opts.no_llm or opts.mock or opts.dry_run):
        summary["warnings"].append("LLM not configured: template personas (no messages, platforms or motivations).")

    first = score_segments(intake, aff)  # rules + affordability + features, before any Qloo signal
    rec.write_json("01_segments_before_qloo.json", {"affordability": aff.to_dict(), "segments": first.to_dict()})

    transport = qloo_transport or (make_transport(mock_reject) if opts.mock else None)
    async with QlooClient(settings, rec, transport=transport, dry_run=opts.dry_run, max_calls=opts.max_calls,
                          concurrency=opts.concurrency, delay=opts.delay, synthetic=opts.mock) as client:
        preset, agent_out = None, None
        if opts.agent and llm is not None:
            from ..agent.loop import run_agent
            from ..agent.tools import Toolbox
            tb = Toolbox(client, intake.location)
            agent_out = await run_agent(llm, tb, intake, {"tier": aff.tier, "price_vs_income_ratio": round(aff.ratio, 4), "country": aff.country_name, "calculated": True},
                                        max_steps=opts.agent_steps, delay=opts.llm_delay)
            rec.write_json("agent/trace.json", {"trace": agent_out["trace"], "notebook": agent_out["notebook"]})
            rec.write_json("agent/ledger.json", agent_out["ledger"])
            rec.write_json("agent/result.json", agent_out["result"])
            cands = _agent_competitors(agent_out["result"]["competitors"], intake, tb)
            from .competitors import vet_anchors
            kept, vet_notes, vet_profiles = await vet_anchors(client, intake, cands, llm)
            agent_out["result"]["competitors"] = [{k: c[k] for k in ("name", "entity_id", "why", "cites")} for c in kept]
            agent_out["result"]["rejected"] += vet_notes
            if len(kept) >= 2:
                preset = {"anchors": kept, "unresolved": [c for c in intake.competitors if c.lower() not in {a["name"].lower() for a in kept}],
                          "notes": vet_notes, "category": None, "profiles": vet_profiles}
            else:
                summary["warnings"].append(f"The agent verified only {len(kept)} competitor(s); the fixed competitor steps were used instead.")
        elif opts.agent:
            summary["warnings"].append("--agent needs the LLM (not configured or disabled): fell back to the fixed competitor steps.")
        anchor = await E.resolve_and_skew(client, intake, llm=llm, discover=opts.discover, preset=preset)
        # re-rank with the Qloo audience fit, then fetch persona evidence only for the final top segments
        scoring = score_segments(intake, aff, E.qloo_fit_from_age_index(anchor["age_index"], list(SEGMENTS))
                                 if anchor["age_index"] else None)
        rec.write_json("02_segments_after_qloo.json", scoring.to_dict())
        await E.gather_segments(client, intake, scoring.ranked, anchor["ev"], opts.kinds, opts.take)
        results, auth_failed, calls_used = client.results, client.auth_failed, client.calls_used

    ev_items = anchor["ev"].items
    if opts.mock:
        for it in ev_items:
            it["synthetic"] = True
    for r in results:
        rec.append_jsonl("calls.jsonl", {"step": r.spec.step, "label": r.spec.label, "path": r.spec.path, "ok": r.ok,
                                         "status": r.status, "variant_index": r.variant_index, "variant_meta": r.meta,
                                         "elapsed_ms": r.elapsed_ms, "error": r.error or r.skipped_reason, "files": r.files})
    rec.write_json("03_evidence.json", ev_items)

    bundle = {"evidence": ev_items, "anchors": anchor["anchors"], "unresolved": anchor["unresolved"],
              "age_index": anchor["age_index"], "gender_index": anchor["gender_index"], "category": anchor.get("category"), "agent": agent_out}
    shared = anchor.get("notes", []) + E.shared_evidence_notes(ev_items, scoring.ranked, intake.location)
    personas = await writer.write_personas(llm, intake, aff, scoring.ranked, bundle, delay=opts.llm_delay)
    attribution = ["World Bank Open Data (CC BY 4.0)"] + ([FX_ATTRIBUTION] if aff.conversion else [])
    rec.write_json("04_personas.json", {"synthetic": opts.mock, "affordability": aff.to_dict(), "personas": personas,
                                        "anchor_audience": {k: bundle[k] for k in ("anchors", "unresolved", "age_index", "gender_index", "category")},
                                        "agent": agent_out["result"] if agent_out else None,
                                        "evidence_notes": shared,
                                        "scoring": {"ranked_by": scoring.ranked_by, "notes": scoring.notes,
                                                    "omitted_by_limit": scoring.omitted_by_limit, "excluded": scoring.excluded},
                                        "attribution": attribution})
    rec.write_text("04_personas.md", writer.markdown(intake, aff, personas, bundle, shared + scoring.notes + aff.caveats,
                                                     attribution, opts.mock))

    ok_calls = sum(1 for r in results if r.ok)
    llm_failed = sum(1 for p in personas if llm and p["source"] != "llm")
    summary.update({
        "status": "dry_run" if opts.dry_run else "auth_failed" if auth_failed else "complete",
        "personas": len(personas), "persona_sources": [p["source"] for p in personas],
        "qloo_calls": len(results), "qloo_ok": ok_calls, "qloo_failed": len(results) - ok_calls, "http_requests": calls_used,
        "llm_calls": llm.calls if llm else 0, "llm_failed_personas": llm_failed,
        "failures": [{"label": r.spec.label, "status": r.status, "error": r.error or r.skipped_reason, "files": r.files}
                     for r in results if not r.ok],
        "seconds": round(time.time() - started, 1)})
    rec.write_json("99_run_summary.json", summary)
    if opts.zip:
        summary["zip"] = shutil.make_archive(str(run_dir), "zip", run_dir.parent, run_dir.name)
    if auth_failed:
        code = 3
    elif opts.dry_run or (results and ok_calls == len(results) and not llm_failed):
        code = 0
    elif results and ok_calls == 0:
        code = 2
    else:
        code = 1
    return code, run_dir, summary
