"""Runs an analysis with the engine in the background and records live progress and the final result in the database."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ...config import Settings
from ...engine.personas.intake import ProductIntake
from ...engine.personas.refdata.store import ReferenceStore
from ...engine.personas.runner import PersonaOptions, execute_personas
from ..models import Analysis, AnalysisEvent
from ..settings import ApiSettings

_TASKS: set[asyncio.Task] = set()


def add_event(sf: sessionmaker[Session], analysis_id: str, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
    with sf() as db:
        n = db.query(AnalysisEvent).filter_by(analysis_id=analysis_id).count()
        db.add(AnalysisEvent(analysis_id=analysis_id, seq=n + 1, stage=stage, message=message[:500], data=data or {}))
        db.commit()


def _finish(sf: sessionmaker[Session], analysis_id: str, **fields: Any) -> None:
    with sf() as db:
        a = db.get(Analysis, analysis_id)
        if a:
            for k, v in fields.items():
                setattr(a, k, v)
            a.finished_at = datetime.now(timezone.utc)
            db.commit()


async def run_analysis(sf: sessionmaker[Session], api: ApiSettings, analysis_id: str, engine_settings: Settings | None = None,
                       llm_transport: Any = None, qloo_transport: Any = None) -> None:
    with sf() as db:
        a = db.get(Analysis, analysis_id)
        if a is None:
            return
        a.status = "running"
        db.commit()
        intake_dict, options = dict(a.intake), dict(a.options or {})
    add_event(sf, analysis_id, "start", "Analysis started")
    out = Path(tempfile.mkdtemp(prefix="run-", dir=_ensure(api.runs_dir)))
    try:
        intake = ProductIntake.from_dict(intake_dict)
        opts = PersonaOptions(intake=intake, out=out, mock=api.mock_engine, zip=False, max_calls=150,
                              discover=bool(options.get("discover", True)),
                              agent=bool(options.get("use_agent", True)) and api.agent_enabled and not api.mock_engine,
                              llm_delay=api.llm_delay,
                              progress=lambda stage, msg, data: add_event(sf, analysis_id, stage, msg, data))
        settings = engine_settings or Settings.from_env()
        code, run_dir, summary = await execute_personas(opts, settings, ReferenceStore(), llm_transport=llm_transport,
                                                        qloo_transport=qloo_transport)
        pj = Path(run_dir) / "04_personas.json"
        if code == 3 or not pj.exists():
            raise RuntimeError("; ".join(summary.get("errors") or []) or summary.get("status") or "the engine could not run")
        result = json.loads(pj.read_text(encoding="utf-8"))
        md = Path(run_dir) / "04_personas.md"
        agent_trace = Path(run_dir) / "agent" / "trace.json"
        if agent_trace.exists():
            result["agent_trace"] = json.loads(agent_trace.read_text(encoding="utf-8")).get("trace", [])
        slim = {k: summary.get(k) for k in ("status", "qloo_calls", "qloo_ok", "qloo_failed", "llm_calls", "warnings", "seconds", "persona_sources")}
        add_event(sf, analysis_id, "done", f"Finished: {len(result.get('personas', []))} personas")
        _finish(sf, analysis_id, status="complete", result=result, summary=slim, report_md=md.read_text(encoding="utf-8") if md.exists() else None)
    except Exception as exc:  # the user sees a short reason; details stay in server logs
        add_event(sf, analysis_id, "error", f"The analysis failed: {exc}"[:400])
        _finish(sf, analysis_id, status="failed", error=str(exc)[:1000])
    finally:
        shutil.rmtree(out, ignore_errors=True)


def _ensure(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def launch(sf: sessionmaker[Session], api: ApiSettings, analysis_id: str, **kw: Any) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(run_analysis(sf, api, analysis_id, **kw))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return task


def fail_stale(sf: sessionmaker[Session]) -> int:
    """Runs die with the process: anything still queued/running at startup can never finish."""
    with sf() as db:
        rows = db.query(Analysis).filter(Analysis.status.in_(("queued", "running"))).all()
        for a in rows:
            a.status, a.error, a.finished_at = "failed", "The server restarted while this analysis was running. Please run it again.", datetime.now(timezone.utc)
        db.commit()
        return len(rows)
