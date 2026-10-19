"""Learned market categories: what worked for a kind of product is tried first next time (fewer model calls, steadier results).

Only confirmed, generic mappings are stored: the product type as a short phrase, the market label, its tier and the Qloo tags
that returned brands. The engine re-checks every stored mapping with live data, so a stale one simply fails and is dropped."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import LearnedCategory

LIMIT = 4


def norm_type(product_type: str, category: str) -> str:
    t = re.sub(r"[^a-z0-9 ]+", " ", (product_type or category or "").lower())
    return re.sub(r"\s+", " ", t).strip()[:80]


def _words(t: str) -> set[str]:
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in t.split() if len(w) > 2}


async def known_for(db: AsyncSession, product_type: str, category: str) -> list[dict[str, Any]]:
    """Stored mappings for this product type (exact), else for the same category with a shared word in the product type."""
    key = norm_type(product_type, category)
    if not key:
        return []
    rows = (await db.execute(select(LearnedCategory).where(LearnedCategory.product_type == key)
                             .order_by(LearnedCategory.hits.desc()).limit(LIMIT))).scalars().all()
    if len(rows) < LIMIT and category:
        words = _words(key)
        more = (await db.execute(select(LearnedCategory).where(LearnedCategory.category == category, LearnedCategory.product_type != key)
                                 .order_by(LearnedCategory.hits.desc()).limit(40))).scalars().all()
        rows += [r for r in more if _words(r.product_type) & words][: LIMIT - len(rows)]
    return [{"label": r.label, "tier": r.tier, "tags": r.tags} for r in rows if r.tags]


async def remember(db: AsyncSession, product_type: str, category: str, learned: list[dict[str, Any]]) -> int:
    """Store (or count another success for) each confirmed label. Returns how many were written."""
    key = norm_type(product_type, category)
    n = 0
    for it in learned or []:
        label = str(it.get("label") or "").strip().lower()[:60]
        tags = [{"id": t["id"], "name": t.get("name")} for t in it.get("tags") or [] if t.get("id")][:2]
        if not key or not label or not tags:
            continue
        row = (await db.execute(select(LearnedCategory).where(LearnedCategory.product_type == key, LearnedCategory.label == label))).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row:
            row.hits, row.tags, row.last_used_at = row.hits + 1, tags, now
        else:
            db.add(LearnedCategory(product_type=key, category=(category or "")[:40], label=label, tier=str(it.get("tier") or "sector")[:20], tags=tags))
        n += 1
    if n:
        await db.commit()
    return n
