from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..schemas import Login, SignUp, TokenOut, UserOut
from ..security import hash_password, make_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token(request: Request, user: User) -> TokenOut:
    s = request.app.state.settings
    return TokenOut(token=make_token(user.id, s.secret_key, s.token_minutes), user=UserOut.model_validate(user))


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(body: SignUp, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    if not request.app.state.settings.allow_signup:
        raise HTTPException(403, "Sign-ups are closed")
    email = body.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return _token(request, user)


@router.post("/login", response_model=TokenOut)
def login(body: Login, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(User).filter_by(email=body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return _token(request, user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
