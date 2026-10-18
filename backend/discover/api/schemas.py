"""Request and response shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignUp(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=120)


class Login(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str


class TokenOut(BaseModel):
    token: str
    user: UserOut


class IntakeIn(BaseModel):
    """Mirrors the engine's ProductIntake; the engine validates the values (category, currency, location...)."""
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=10, max_length=1000)
    category: str
    price: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    location: str = Field(min_length=1, max_length=120)
    purchase_type: str = "one_off"
    purchases_per_year: float | None = None
    country: str | None = None
    features: list[str] = Field(default_factory=list, max_length=12)
    competitors: list[str] = Field(default_factory=list, max_length=10)
    product_type: str = Field(default="", max_length=80)
    competitor_prices: list[float] = Field(default_factory=list, max_length=10)
    max_personas: int = Field(default=6, ge=1, le=10)
    gender_focus: str | None = None
    age_focus: list[str] = Field(default_factory=list)


class RunOptions(BaseModel):
    use_agent: bool = True  # let the LLM explore Qloo with tools (falls back to the fixed steps)
    discover: bool = True  # look for more competitors in Qloo than the ones listed


class AnalysisCreate(BaseModel):
    intake: IntakeIn
    options: RunOptions = Field(default_factory=RunOptions)


class AnalysisCreated(BaseModel):
    id: str
    status: str


class AnalysisListItem(BaseModel):
    id: str
    title: str
    status: str
    product: str
    location: str
    persona_count: int
    created_at: datetime
    finished_at: datetime | None = None


class EventOut(BaseModel):
    seq: int
    stage: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EventsOut(BaseModel):
    status: str
    events: list[EventOut]


class AnalysisOut(BaseModel):
    id: str
    title: str
    status: str
    intake: dict[str, Any]
    options: dict[str, Any]
    result: dict[str, Any] | None = None  # persona edits already applied
    summary: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class PersonaEdit(BaseModel):
    display_name: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=400)
