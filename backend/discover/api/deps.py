from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import Analysis, User
from .security import read_token


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token", "")
    uid = read_token(token, request.app.state.settings.secret_key) if token else None
    user = await db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return user


async def owned_analysis(analysis_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> Analysis:
    a = await db.get(Analysis, analysis_id)
    if a is None or a.user_id != user.id:  # same answer for "missing" and "not yours"
        raise HTTPException(404, "Analysis not found")
    return a


def is_admin(user: User, request: Request) -> bool:
    return user.email.lower() in request.app.state.settings.admin_emails


async def admin_user(request: Request, user: User = Depends(current_user)) -> User:
    if not is_admin(user, request):
        raise HTTPException(404, "Not found")  # same answer as a missing page: do not reveal that an admin area exists
    return user
