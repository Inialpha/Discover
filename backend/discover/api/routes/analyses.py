from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...engine.personas.intake import ProductIntake
from ..db import get_db
from ..deps import current_user, owned_analysis
from ..models import Analysis, AnalysisEvent, Product, User
from ..schemas import (AnalysisCreate, AnalysisCreated, AnalysisListItem, AnalysisOut, EventOut, EventsOut, PersonaEdit)
from ..services import products as prod
from ..services import runner
from ..services.views import EDITABLE, merged_result

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


def _title(intake: dict) -> str:
    return f"{intake['name']} · {intake['location']}"[:200]


@router.post("", response_model=AnalysisCreated, status_code=202)
async def create(body: AnalysisCreate, request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> AnalysisCreated:
    st = request.app.state.settings
    intake = ProductIntake.from_dict(body.intake.model_dump())
    problems = intake.validate()
    if problems:
        raise HTTPException(422, {"message": "Please fix these fields", "problems": problems})
    active = (await db.execute(select(func.count()).select_from(Analysis).where(Analysis.user_id == user.id, Analysis.status.in_(("queued", "running"))))).scalar_one()
    if active >= 1:
        raise HTTPException(429, "You already have an analysis running. Wait for it to finish.")
    since = datetime.now(timezone.utc) - timedelta(days=1)
    recent = (await db.execute(select(func.count()).select_from(Analysis).where(Analysis.user_id == user.id, Analysis.created_at >= since))).scalar_one()
    if recent >= st.max_runs_per_day:
        raise HTTPException(429, f"Daily limit of {st.max_runs_per_day} analyses reached. Try again tomorrow.")
    data = body.intake.model_dump()
    if body.product_id:  # run again for a product the user already has
        product = await prod.owned_product(db, body.product_id, user.id)
        number, latest = await prod.next_run(db, product.id)
        base = latest
        if body.based_on:
            base = await db.get(Analysis, body.based_on)
            if base is None or base.product_id != product.id:
                raise HTTPException(404, "The run to copy from was not found in this product")
        changes = prod.diff_intake(base.intake if base else None, data)
        prod.touch(product)
    else:
        product = Product(user_id=user.id, name=data["name"][:120])
        db.add(product)
        await db.flush()
        number, changes = 1, []
    a = Analysis(user_id=user.id, product_id=product.id, run_number=number, changes=changes, title=_title(data), intake=data,
                 options=body.options.model_dump(), status="queued")
    db.add(a)
    await db.commit()
    runner.launch(request.app.state.session_factory, st, a.id, **request.app.state.engine_kwargs)
    return AnalysisCreated(id=a.id, status=a.status, product_id=product.id, run_number=number)


@router.get("", response_model=list[AnalysisListItem])
async def list_mine(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[AnalysisListItem]:
    rows = (await db.execute(select(Analysis).where(Analysis.user_id == user.id).order_by(Analysis.created_at.desc()).limit(100))).scalars().all()
    return [AnalysisListItem(id=a.id, product_id=a.product_id, run_number=a.run_number, title=a.title, status=a.status, product=a.intake.get("name", ""), location=a.intake.get("location", ""),
                             persona_count=len((a.result or {}).get("personas", [])), created_at=a.created_at, finished_at=a.finished_at)
            for a in rows]


@router.get("/{analysis_id}", response_model=AnalysisOut)
async def get_one(a: Analysis = Depends(owned_analysis), db: AsyncSession = Depends(get_db)) -> AnalysisOut:
    product = await db.get(Product, a.product_id) if a.product_id else None
    count = await prod.run_count(db, a.product_id) if a.product_id else 1
    return AnalysisOut(id=a.id, product_id=a.product_id, product_name=product.name if product else None, run_number=a.run_number,
                       run_count=count, changes=a.changes or [], title=a.title, status=a.status, intake=a.intake, options=a.options or {}, result=merged_result(a),
                       summary=a.summary, error=a.error, created_at=a.created_at, finished_at=a.finished_at)


@router.get("/{analysis_id}/events", response_model=EventsOut)
async def events(since: int = 0, a: Analysis = Depends(owned_analysis), db: AsyncSession = Depends(get_db)) -> EventsOut:
    rows = (await db.execute(select(AnalysisEvent).where(AnalysisEvent.analysis_id == a.id, AnalysisEvent.seq > since).order_by(AnalysisEvent.seq))).scalars().all()
    await db.refresh(a)
    return EventsOut(status=a.status, events=[EventOut(seq=e.seq, stage=e.stage, message=e.message, data=e.data or {}, created_at=e.created_at) for e in rows])


@router.patch("/{analysis_id}/personas/{index}", response_model=AnalysisOut)
async def edit_persona(index: int, body: PersonaEdit, a: Analysis = Depends(owned_analysis), db: AsyncSession = Depends(get_db)) -> AnalysisOut:
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
    await db.commit()
    return await get_one(a, db)


@router.delete("/{analysis_id}", status_code=204)
async def delete(a: Analysis = Depends(owned_analysis), db: AsyncSession = Depends(get_db)) -> None:
    await db.execute(sa_delete(AnalysisEvent).where(AnalysisEvent.analysis_id == a.id))
    pid = a.product_id
    await db.delete(a)
    await db.flush()
    if pid and await prod.run_count(db, pid) == 0:  # the last run of a product takes the product with it
        p = await db.get(Product, pid)
        if p:
            await db.delete(p)
    await db.commit()
