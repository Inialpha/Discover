"""Runs an analysis with the engine in the background and records live progress and the final result in the database."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...config import Settings
from ...engine.personas.intake import ProductIntake
from ...engine.personas.refdata.store import ReferenceStore
from ...engine.personas.runner import PersonaOptions, execute_personas
from ..models import Analysis, AnalysisEvent
from . import categories
from ..settings import ApiSettings

_TASKS: set[asyncio.Task] = set()
SF = async_sessionmaker[AsyncSession]


async def add_event(sf: SF, analysis_id: str, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
    async with sf() as db:
        n = (await db.execute(select(func.coalesce(func.max(AnalysisEvent.seq), 0)).where(AnalysisEvent.analysis_id == analysis_id))).scalar_one()
        db.add(AnalysisEvent(analysis_id=analysis_id, seq=n + 1, stage=stage, message=message[:500], data=data or {}))
        await db.commit()


class EventWriter:
    """The engine reports progress through a plain (synchronous) callback. It must not touch the database on the event loop,
    so the callback only queues the event and this task writes them, in order, with async database calls."""

    def __init__(self, sf: SF, analysis_id: str):
        self.sf, self.analysis_id = sf, analysis_id
        self.queue: asyncio.Queue[tuple[str, str, dict[str, Any]] | None] = asyncio.Queue()
        self.task = asyncio.get_running_loop().create_task(self._drain())

    def callback(self, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
        self.queue.put_nowait((stage, message, data or {}))

    async def _drain(self) -> None:
        while (item := await self.queue.get()) is not None:
            for attempt in range(3):  # a busy database must not lose a progress line; a persistent failure must not break the run
                try:
                    await add_event(self.sf, self.analysis_id, *item)
                    break
                except Exception:
                    await asyncio.sleep(0.2 * (attempt + 1))

    async def close(self) -> None:
        self.queue.put_nowait(None)
        await self.task


async def _finish(sf: SF, analysis_id: str, **fields: Any) -> None:
    async with sf() as db:
        await db.execute(update(Analysis).where(Analysis.id == analysis_id).values(finished_at=datetime.now(timezone.utc), **fields))
        await db.commit()


async def run_analysis(sf: SF, api: ApiSettings, analysis_id: str, engine_settings: Settings | None = None,
                       llm_transport: Any = None, qloo_transport: Any = None) -> None:
    async with sf() as db:
        a = await db.get(Analysis, analysis_id)
        if a is None:
            return
        a.status = "running"
        await db.commit()
        intake_dict, options = dict(a.intake), dict(a.options or {})
        try:
            known = await categories.known_for(db, intake_dict.get("product_type", ""), intake_dict.get("category", ""))
        except Exception:  # an optional speed-up: never block a run
            known = []
    writer = EventWriter(sf, analysis_id)
    writer.callback("start", "Analysis started")
    out = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="run-", dir=_ensure(api.runs_dir)))
    try:
        intake = ProductIntake.from_dict(intake_dict)
        opts = PersonaOptions(intake=intake, out=out, mock=api.mock_engine, zip=False, max_calls=150,
                              discover=bool(options.get("discover", True)),
                              agent=bool(options.get("use_agent", True)) and api.agent_enabled and not api.mock_engine,
                              llm_delay=api.llm_delay, progress=writer.callback, known_categories=known)
        settings = engine_settings or Settings.from_env()
        code, run_dir, summary = await execute_personas(opts, settings, ReferenceStore(), llm_transport=llm_transport,
                                                        qloo_transport=qloo_transport)
        pj = Path(run_dir) / "04_personas.json"
        if code == 3 or not pj.exists():
            raise RuntimeError("; ".join(summary.get("errors") or []) or summary.get("status") or "the engine could not run")
        result, md_text = await asyncio.to_thread(_read_outputs, Path(run_dir))
        slim = {k: summary.get(k) for k in ("status", "qloo_calls", "qloo_ok", "qloo_failed", "llm_calls", "warnings", "seconds", "persona_sources", "llm_fallbacks")}
        try:
            async with sf() as db:
                await categories.remember(db, intake_dict.get("product_type", ""), intake_dict.get("category", ""), summary.get("learned_categories") or [])
        except Exception:
            pass
        writer.callback("done", f"Finished: {len(result.get('personas', []))} personas")
        await writer.close()
        await _finish(sf, analysis_id, status="complete", result=result, summary=slim, report_md=md_text)
    except asyncio.CancelledError:
        await writer.close()
        await _finish(sf, analysis_id, status="failed", error="The server stopped while this analysis was running. Please run it again.")
        raise
    except Exception as exc:  # the user sees a short reason; details stay in server logs
        writer.callback("error", f"The analysis failed: {exc}"[:400])
        await writer.close()
        await _finish(sf, analysis_id, status="failed", error=str(exc)[:1000])
    finally:
        await asyncio.to_thread(shutil.rmtree, out, ignore_errors=True)


def _read_outputs(run_dir: Path) -> tuple[dict[str, Any], str | None]:
    result = json.loads((run_dir / "04_personas.json").read_text(encoding="utf-8"))
    trace = run_dir / "agent" / "trace.json"
    if trace.exists():
        result["agent_trace"] = json.loads(trace.read_text(encoding="utf-8")).get("trace", [])
    md = run_dir / "04_personas.md"
    return result, md.read_text(encoding="utf-8") if md.exists() else None


def _ensure(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def launch(sf: SF, api: ApiSettings, analysis_id: str, **kw: Any) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(run_analysis(sf, api, analysis_id, **kw))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return task


async def cancel_all() -> None:
    tasks = list(_TASKS)
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def fail_stale(sf: SF) -> int:
    """Runs die with the process: anything still queued/running at startup can never finish."""
    async with sf() as db:
        res = await db.execute(update(Analysis).where(Analysis.status.in_(("queued", "running"))).values(
            status="failed", error="The server restarted while this analysis was running. Please run it again.", finished_at=datetime.now(timezone.utc)))
        await db.commit()
        return res.rowcount or 0
