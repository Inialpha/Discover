from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import current_user, is_admin
from ..models import User
from ..google import GoogleAuthError, verify_google
from ..schemas import GoogleLogin, Login, SignUp, TokenOut, UserOut
from ..security import hash_password, make_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _out(request: Request, user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.is_admin = is_admin(user, request)
    return out


def _token(request: Request, user: User) -> TokenOut:
    s = request.app.state.settings
    return TokenOut(token=make_token(user.id, s.secret_key, s.token_minutes), user=_out(request, user))


@router.post("/signup", response_model=TokenOut, status_code=201)
async def signup(body: SignUp, request: Request, db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not request.app.state.settings.allow_signup:
        raise HTTPException(403, "Sign-ups are closed")
    email = body.email.lower()
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=await asyncio.to_thread(hash_password, body.password))
    db.add(user)
    await db.commit()
    return _token(request, user)


@router.post("/login", response_model=TokenOut)
async def login(body: Login, request: Request, db: AsyncSession = Depends(get_db)) -> TokenOut:
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if not user or not await asyncio.to_thread(verify_password, body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return _token(request, user)


@router.post("/google", response_model=TokenOut)
async def google(body: GoogleLogin, request: Request, db: AsyncSession = Depends(get_db)) -> TokenOut:
    """Sign in (or sign up) with a Google ID token. An existing account with the same verified email is signed in; a new one needs
    sign-ups to be open. Google accounts get no usable password, so the password form cannot be used for them."""
    st = request.app.state.settings
    try:
        info = await verify_google(body.credential, st.google_client_id)
    except GoogleAuthError as exc:
        raise HTTPException(401, str(exc))
    user = (await db.execute(select(User).where(User.email == info["email"]))).scalar_one_or_none()
    if user is None:
        if not st.allow_signup:
            raise HTTPException(403, "Sign-ups are closed")
        user = User(email=info["email"], name=info["name"], password_hash="google")
        db.add(user)
        await db.commit()
    return _token(request, user)


@router.get("/me", response_model=UserOut)
async def me(request: Request, user: User = Depends(current_user)) -> UserOut:
    return _out(request, user)
