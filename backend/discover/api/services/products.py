"""Products group the runs of one product. A run is an Analysis row whose product_id points at its Product."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Analysis, Product

# (field, how it reads in the "what changed" line)
_FIELDS = [("name", "name"), ("description", "description"), ("category", "category"), ("product_type", "product type"),
           ("location", "location"), ("purchase_type", "how it is bought"), ("purchases_per_year", "purchases per year"),
           ("features", "features"), ("competitors", "competitors"), ("max_personas", "number of personas"),
           ("gender_focus", "gender focus"), ("age_focus", "age focus")]


def _show(v: Any) -> str:
    if v is None or v == "" or v == []:
        return "none"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else str(v)


def diff_intake(old: dict[str, Any] | None, new: dict[str, Any]) -> list[str]:
    """Short readable lines for what differs between two runs, e.g. 'price 40,000 → 45,000 NGN'. [] for a first run."""
    if not old:
        return []
    out: list[str] = []
    if old.get("price") != new.get("price") or old.get("currency") != new.get("currency"):
        cur = new.get("currency", "")
        if old.get("currency") != new.get("currency"):
            out.append(f"price {_show(old.get('price'))} {old.get('currency', '')} → {_show(new.get('price'))} {cur}")
        else:
            out.append(f"price {_show(old.get('price'))} → {_show(new.get('price'))} {cur}")
    for key, label in _FIELDS:
        a, b = old.get(key), new.get(key)
        if (a or None) != (b or None) and (a or []) != (b or []):
            if key == "description":
                out.append("description changed")
            else:
                out.append(f"{label} {_show(a)} → {_show(b)}")
    return out


async def owned_product(db: AsyncSession, product_id: str, user_id: str) -> Product:
    p = await db.get(Product, product_id)
    if p is None or p.user_id != user_id:  # same answer for "missing" and "not yours"
        raise HTTPException(404, "Product not found")
    return p


async def next_run(db: AsyncSession, product_id: str) -> tuple[int, Analysis | None]:
    """(next run number, the latest run so far)."""
    last = (await db.execute(select(Analysis).where(Analysis.product_id == product_id).order_by(Analysis.run_number.desc()).limit(1))).scalars().first()
    return (last.run_number + 1 if last else 1), last


async def run_count(db: AsyncSession, product_id: str) -> int:
    return (await db.execute(select(func.count()).select_from(Analysis).where(Analysis.product_id == product_id))).scalar_one()


def touch(p: Product) -> None:
    p.updated_at = datetime.now(timezone.utc)
