from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...engine.personas.intake import ProductIntake
from ..db import get_db
from ..deps import current_user, owned_analysis
from ..models import Analysis, AnalysisEvent, User
from ..schemas import (AnalysisCreate, AnalysisCreated, AnalysisListItem, AnalysisOut, EventOut, EventsOut, PersonaEdit)
from ..services import runner
from ..services.views import EDITABLE, merged_result

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


def _title(intake: dict) -> str:
    return f"{intake['name']} · {intake['location']}"[:200]


@router.post("", response_model=AnalysisCreated, status_code=202)
async def create(body: AnalysisCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> AnalysisCreated:
    st = request.app.state.settings
    intake = ProductIntake.from_dict(body.intake.model_dump())
    problems = intake.validate()
    if problems:
        raise HTTPException(422, {"message": "Please fix these fields", "problems": problems})
    if db.query(Analysis).filter(Analysis.user_id == user.id, Analysis.status.in_(("queued", "running"))).count() >= 1:
        raise HTTPException(429, "You already have an analysis running. Wait for it to finish.")
    since = datetime.now(timezone.utc) - timedelta(days=1)
    recent = db.query(Analysis).filter(Analysis.user_id == user.id, Analysis.created_at >= since).count()
    if recent >= st.max_runs_per_day:
        raise HTTPException(429, f"Daily limit of {st.max_runs_per_day} analyses reached. Try again tomorrow.")
    a = Analysis(user_id=user.id, title=_title(body.intake.model_dump()), intake=body.intake.model_dump(), options=body.options.model_dump(),
                 status="queued")
    db.add(a)
    db.commit()
    runner.launch(request.app.state.session_factory, st, a.id, **request.app.state.engine_kwargs)
    return AnalysisCreated(id=a.id, status=a.status)


@router.get("", response_model=list[AnalysisListItem])
def list_mine(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[AnalysisListItem]:
    rows = db.query(Analysis).filter_by(user_id=user.id).order_by(Analysis.created_at.desc()).limit(100).all()
    return [AnalysisListItem(id=a.id, title=a.title, status=a.status, product=a.intake.get("name", ""), location=a.intake.get("location", ""),
                             persona_count=len((a.result or {}).get("personas", [])), created_at=a.created_at, finished_at=a.finished_at)
            for a in rows]


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_one(a: Analysis = Depends(owned_analysis)) -> AnalysisOut:
    return AnalysisOut(id=a.id, title=a.title, status=a.status, intake=a.intake, options=a.options or {}, result=merged_result(a),
                       summary=a.summary, error=a.error, created_at=a.created_at, finished_at=a.finished_at)


@router.get("/{analysis_id}/events", response_model=EventsOut)
def events(since: int = 0, a: Analysis = Depends(owned_analysis), db: Session = Depends(get_db)) -> EventsOut:
    rows = db.query(AnalysisEvent).filter(AnalysisEvent.analysis_id == a.id, AnalysisEvent.seq > since).order_by(AnalysisEvent.seq).all()
    db.refresh(a)
    return EventsOut(status=a.status, events=[EventOut(seq=e.seq, stage=e.stage, message=e.message, data=e.data or {}, created_at=e.created_at) for e in rows])


@router.patch("/{analysis_id}/personas/{index}", response_model=AnalysisOut)
def edit_persona(index: int, body: PersonaEdit, a: Analysis = Depends(owned_analysis), db: Session = Depends(get_db)) -> AnalysisOut:
    personas = (a.result or {}).get("personas") or []
    if not 0 <= index < len(personas):
        raise HTTPException(404, "Persona not found")
    edits = dict(a.edits or {})
    cur = dict(edits.get(str(index), {}))
    for f in EDITABLE:
        v = getattr(body, f)
        if v is not None:
            if v.strip():
                cur[f] = v.strip()
            else:
                cur.pop(f, None)  # an empty value resets the field to the generated text
    edits[str(index)] = cur
    a.edits = edits
    db.commit()
    return get_one(a)


@router.delete("/{analysis_id}", status_code=204)
def delete(a: Analysis = Depends(owned_analysis), db: Session = Depends(get_db)) -> None:
    db.delete(a)
    db.commit()
