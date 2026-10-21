"""Admin dashboard data: who is using Discover, whether analyses are being created and finishing. Admin accounts are listed in
ADMIN_EMAILS. Nothing here returns an analysis's results, report or intake text: only counts, labels, timings and error lines."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import admin_user
from ..models import Analysis, User

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _utc(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def _top(c: Counter, n: int = 8) -> list[dict]:
    return [{"label": k or "(none)", "count": v} for k, v in c.most_common(n)]


@router.get("/overview")
async def overview(days: int = 14, recent: int = 40, _: User = Depends(admin_user), db: AsyncSession = Depends(get_db)) -> dict:
    days, recent = max(1, min(days, 90)), max(1, min(recent, 200))
    now = datetime.now(timezone.utc)
    users = (await db.execute(select(User.id, User.email, User.name, User.created_at))).all()
    rows = (await db.execute(
        select(Analysis.id, Analysis.user_id, Analysis.title, Analysis.status, Analysis.intake, Analysis.options, Analysis.summary,
               Analysis.error, Analysis.created_at, Analysis.finished_at, Analysis.run_number).order_by(Analysis.created_at.desc()))).all()
    email = {u.id: u.email for u in users}

    status = Counter(r.status for r in rows)
    done = status["complete"] + status["failed"]
    day_keys = [(now - timedelta(days=i)).date().isoformat() for i in range(days - 1, -1, -1)]
    per_day: dict[str, dict] = {d: {"day": d, "analyses": 0, "complete": 0, "failed": 0, "signups": 0} for d in day_keys}
    for r in rows:
        d = _utc(r.created_at).date().isoformat()
        if d in per_day:
            per_day[d]["analyses"] += 1
            if r.status in ("complete", "failed"):
                per_day[d][r.status] += 1
    for u in users:
        d = _utc(u.created_at).date().isoformat()
        if d in per_day:
            per_day[d]["signups"] += 1

    secs, qloo, llm = [], [], []
    for r in rows:
        s = r.summary or {}
        if r.status == "complete":
            if isinstance(s.get("seconds"), (int, float)):
                secs.append(float(s["seconds"]))
            if isinstance(s.get("qloo_calls"), int):
                qloo.append(s["qloo_calls"])
            if isinstance(s.get("llm_calls"), int):
                llm.append(s["llm_calls"])
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None  # noqa: E731

    last_seen: dict[str, datetime] = {}
    per_user: Counter = Counter()
    for r in rows:
        per_user[r.user_id] += 1
        last_seen.setdefault(r.user_id, _utc(r.created_at))
    week_ago = now - timedelta(days=7)

    def intake(r, k):
        return (r.intake or {}).get(k) or ""

    latest = []
    for r in rows[:recent]:
        s = r.summary or {}
        fin, cre = _utc(r.finished_at), _utc(r.created_at)
        latest.append({
            "id": r.id, "user": email.get(r.user_id, "?"), "product": intake(r, "name") or r.title, "run": r.run_number,
            "category": intake(r, "category"), "location": intake(r, "location"), "status": r.status,
            "agent": bool((r.options or {}).get("use_agent")), "created_at": cre.isoformat() if cre else None,
            "seconds": s.get("seconds") if isinstance(s.get("seconds"), (int, float)) else (round((fin - cre).total_seconds()) if fin and cre else None),
            "qloo_calls": s.get("qloo_calls"), "llm_calls": s.get("llm_calls"), "warnings": len(s.get("warnings") or []),
            "error": (r.error or "")[:300] or None})
    return {
        "generated_at": now.isoformat(),
        "totals": {"users": len(users), "analyses": len(rows), "complete": status["complete"], "failed": status["failed"],
                   "running": status["running"] + status["queued"],
                   "success_rate": round(status["complete"] / done, 3) if done else None,
                   "active_users_7d": sum(1 for u, t in last_seen.items() if t >= week_ago),
                   "users_with_analyses": len(per_user), "avg_seconds": avg(secs), "avg_qloo_calls": avg(qloo), "avg_llm_calls": avg(llm),
                   "qloo_calls_total": sum(qloo)},
        "per_day": list(per_day.values()),
        "top_locations": _top(Counter(intake(r, "location") for r in rows)),
        "top_categories": _top(Counter(intake(r, "category") for r in rows)),
        "recent": latest,
        "recent_failures": [x for x in latest if x["status"] == "failed"][:10],
        "users": [{"email": u.email, "name": u.name, "joined": _utc(u.created_at).isoformat(), "analyses": per_user.get(u.id, 0),
                   "last_analysis": last_seen[u.id].isoformat() if u.id in last_seen else None}
                  for u in sorted(users, key=lambda u: -(per_user.get(u.id, 0)))][:100],
    }
