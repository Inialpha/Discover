"""End-to-end run orchestration (business mode). Writes everything into one run folder."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .llm.client import LLMClient, LLMError
from .modes.business import brief as B, prompts
from .modes.business.pipeline import ALL_STEPS, run_pipeline
from .modes.business.coverage import coverage_markdown, probe_coverage, report_coverage
from .modes.business.synthesis import synthesize, to_markdown
from .qloo.client import QlooClient
from .qloo.mock import make_transport
from .recorder import RunRecorder, slugify


@dataclass
class RunOptions:
    question: str
    out: Path = Path("runs")
    product: str | None = None
    own_brand: str | None = None
    keywords: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)
    gender: str | None = None
    age: str | None = None
    domains: list[str] | None = None
    take: int = 10
    steps: list[str] | None = None
    skip: list[str] = field(default_factory=list)
    no_llm: bool = False
    mock: bool = False
    dry_run: bool = False
    plan_only: bool = False
    max_calls: int = 80
    concurrency: int = 2
    delay: float = 0.0
    zip: bool = True
    location_mode: str = "auto"


async def execute(opts: RunOptions, settings: Settings, mock_reject=None) -> tuple[int, Path, dict[str, Any]]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = opts.out / f"{stamp}_{slugify(opts.question)}"
    rec = RunRecorder(run_dir)
    from .qloo import calls as _calls
    _calls.set_location_mode(opts.location_mode)
    started = time.time()
    rec.write_json("00_input.json", {
        **{k: (str(v) if isinstance(v, Path) else v) for k, v in opts.__dict__.items()},
        "qloo_base_url": settings.qloo_base_url, "qloo_key_present": bool(settings.qloo_api_key),
        "llm_model": settings.llm_model, "llm_configured": settings.llm_configured,
    })
    summary: dict[str, Any] = {"run_dir": str(run_dir), "synthetic": opts.mock, "warnings": []}

    llm: LLMClient | None = None
    if settings.llm_configured and not opts.no_llm and not opts.mock:
        llm = LLMClient(settings, rec)
    elif not opts.no_llm and not opts.mock:
        summary["warnings"].append("LLM not configured: heuristic planner + template report used.")

    # 1. plan
    brief = B.heuristic_brief(opts.question)
    if llm:
        try:
            data = await llm.chat_json("planner", prompts.PLANNER_SYSTEM, opts.question, max_tokens=800)
            brief = B.brief_from_llm(opts.question, data)
        except LLMError as exc:
            summary["warnings"].append(f"LLM planner failed ({exc}); heuristic used.")
    brief = B.apply_overrides(
        brief, product=opts.product, own_brand=opts.own_brand, keywords=opts.keywords,
        competitors=opts.competitors, interests=opts.interests, locations=opts.locations,
        segments=opts.segments, gender=opts.gender, age=opts.age, domains=opts.domains)
    rec.write_json("01_brief.json", brief.to_dict())
    if opts.plan_only:
        summary["status"] = "plan_only"
        rec.write_json("99_run_summary.json", summary)
        return 0, run_dir, summary

    if not (settings.qloo_api_key or opts.mock or opts.dry_run):
        summary["status"] = "no_qloo_key"
        summary["warnings"].append("QLOO_API_KEY missing. Use --mock or --dry-run, or set the key.")
        rec.write_json("99_run_summary.json", summary)
        return 3, run_dir, summary

    steps = set(opts.steps or ALL_STEPS) - set(opts.skip)
    transport = make_transport(mock_reject) if opts.mock else None
    async with QlooClient(settings, rec, transport=transport, dry_run=opts.dry_run, max_calls=opts.max_calls,
                          concurrency=opts.concurrency, delay=opts.delay, synthetic=opts.mock) as client:
        ev, resolved = await run_pipeline(client, brief, steps, take=opts.take)
        results = client.results
        calls_used, auth_failed = client.calls_used, client.auth_failed

    for r in results:
        rec.append_jsonl("calls.jsonl", {
            "step": r.spec.step, "label": r.spec.label, "path": r.spec.path, "ok": r.ok, "status": r.status,
            "variant_index": r.variant_index, "variant_meta": r.meta, "elapsed_ms": r.elapsed_ms,
            "error": r.error or r.skipped_reason, "files": r.files})
    if opts.mock:
        for it in ev.items:
            it["synthetic"] = True
    rec.write_json("02_resolved.json", resolved.__dict__)
    rec.write_json("03_evidence.json", ev.items)

    # 2. synthesize
    report, mode = await synthesize(llm, brief, ev.items)
    if opts.mock:
        report.setdefault("caveats", []).insert(0, "SYNTHETIC DATA: produced by --mock, not by Qloo.")
    report["data_coverage"] = report_coverage(ev.items, brief.locations)
    rec.write_json("04_report.json", {"mode": mode, "report": report})
    rec.write_text("04_report.md", to_markdown(brief, report, ev.items, mode))

    ok_calls = sum(1 for r in results if r.ok)
    dry = opts.dry_run
    summary.update({
        "status": "dry_run" if dry else "auth_failed" if auth_failed else "complete",
        "report_mode": mode, "qloo_calls": len(results), "qloo_ok": ok_calls, "qloo_failed": len(results) - ok_calls,
        "http_requests": calls_used, "llm_calls": llm.calls if llm else 0,
        "variants_used": [{"label": r.spec.label, "variant": r.variant_index, **r.meta} for r in results if r.ok],
        "failures": [{"label": r.spec.label, "status": r.status, "error": r.error or r.skipped_reason, "files": r.files}
                     for r in results if not r.ok],
        "seconds": round(time.time() - started, 1),
    })
    rec.write_json("99_run_summary.json", summary)
    if opts.zip:
        summary["zip"] = shutil.make_archive(str(run_dir), "zip", run_dir.parent, run_dir.name)
    code = 3 if auth_failed else 0 if dry or (results and ok_calls == len(results)) else 2 if ok_calls == 0 else 1
    return code, run_dir, summary


async def execute_coverage(locations: list[str], gender: str | None, age: str | None, kinds: list[str], take: int,
                           out: Path, settings: Settings, mock: bool = False, max_calls: int = 150,
                           concurrency: int = 2, delay: float = 0.0, location_mode: str = "auto", zip_: bool = True):
    from .qloo import calls as _calls
    _calls.set_location_mode(location_mode)
    run_dir = out / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_coverage"
    rec = RunRecorder(run_dir)
    rec.write_json("00_input.json", {"locations": locations, "gender": gender, "age": age, "kinds": kinds, "take": take,
                                     "mock": mock, "location_mode": location_mode, "qloo_base_url": settings.qloo_base_url})
    if not (settings.qloo_api_key or mock):
        return 3, run_dir, {"status": "no_qloo_key"}
    async with QlooClient(settings, rec, transport=make_transport() if mock else None, max_calls=max_calls,
                          concurrency=concurrency, delay=delay, synthetic=mock) as client:
        res = await probe_coverage(client, locations, gender, age, kinds, take)
        auth_failed = client.auth_failed
    rec.write_json("coverage.json", {"synthetic": mock, **res})
    rec.write_text("coverage.md", coverage_markdown(res, mock))
    summary = {"status": "auth_failed" if auth_failed else "complete", "errors": len(res["errors"]), "run_dir": str(run_dir)}
    rec.write_json("99_run_summary.json", summary)
    if zip_:
        summary["zip"] = shutil.make_archive(str(run_dir), "zip", run_dir.parent, run_dir.name)
    return (3 if auth_failed else 1 if res["errors"] else 0), run_dir, summary
