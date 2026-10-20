"""Products: the parent of a product's runs. The history page lists products; a product page lists its runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import current_user
from ..models import Analysis, AnalysisEvent, Product, User
from ..schemas import ProductEdit, ProductListItem, ProductOut, RunItem
from ..services import products as prod
from ..services.views import merged_result

router = APIRouter(prefix="/api/products", tags=["products"])


def _run_item(a: Analysis) -> RunItem:
    res = merged_result(a) if a.result else None
    personas = (res or {}).get("personas", [])
    return RunItem(id=a.id, run_number=a.run_number, status=a.status, changes=a.changes or [], price=float(a.intake.get("price", 0)),
                   currency=a.intake.get("currency", ""), location=a.intake.get("location", ""), persona_count=len(personas),
                   persona_names=[p.get("display_name", "") for p in personas][:6], created_at=a.created_at, finished_at=a.finished_at)


@router.get("", response_model=list[ProductListItem])
async def list_products(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[ProductListItem]:
    products = (await db.execute(select(Product).where(Product.user_id == user.id).order_by(Product.updated_at.desc()).limit(100))).scalars().all()
    if not products:
        return []
    ids = [p.id for p in products]
    # only the light columns: results can be large and the list does not need them
    rows = (await db.execute(select(Analysis.id, Analysis.product_id, Analysis.run_number, Analysis.status, Analysis.intake)
                             .where(Analysis.product_id.in_(ids)).order_by(Analysis.run_number))).all()
    runs: dict[str, list] = {}
    for r in rows:
        runs.setdefault(r.product_id, []).append(r)
    out = []
    for p in products:
        rs = runs.get(p.id) or []
        if not rs:
            continue
        last = rs[-1]
        out.append(ProductListItem(id=p.id, name=p.name, run_count=len(rs), location=last.intake.get("location", ""),
                                   price=float(last.intake.get("price", 0)), currency=last.intake.get("currency", ""),
                                   latest_run_id=last.id, latest_status=last.status, created_at=p.created_at, updated_at=p.updated_at))
    return out


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> ProductOut:
    p = await prod.owned_product(db, product_id, user.id)
    runs = (await db.execute(select(Analysis).where(Analysis.product_id == p.id).order_by(Analysis.run_number.desc()))).scalars().all()
    return ProductOut(id=p.id, name=p.name, created_at=p.created_at, runs=[_run_item(a) for a in runs])


@router.patch("/{product_id}", response_model=ProductOut)
async def rename_product(product_id: str, body: ProductEdit, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> ProductOut:
    p = await prod.owned_product(db, product_id, user.id)
    p.name = body.name.strip()
    prod.touch(p)
    await db.commit()
    return await get_product(product_id, user, db)


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> None:
    p = await prod.owned_product(db, product_id, user.id)
    run_ids = (await db.execute(select(Analysis.id).where(Analysis.product_id == p.id))).scalars().all()
    if run_ids:  # SQLite does not enforce ON DELETE CASCADE by default, so remove the children explicitly
        await db.execute(sa_delete(AnalysisEvent).where(AnalysisEvent.analysis_id.in_(run_ids)))
        await db.execute(sa_delete(Analysis).where(Analysis.id.in_(run_ids)))
    await db.delete(p)
    await db.commit()
