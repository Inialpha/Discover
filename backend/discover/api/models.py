"""Tables. Results are stored as JSON so the engine's output can evolve without migrations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued | running | complete | failed
    intake: Mapped[dict] = mapped_column(JSON)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # the engine's 04_personas.json (+ agent trace)
    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # run counters and warnings
    edits: Mapped[dict] = mapped_column(JSON, default=dict)  # {"<persona index>": {"display_name"?, "title"?, "summary"?}}
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship(back_populates="analyses")
    events: Mapped[list["AnalysisEvent"]] = relationship(back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True,
                                                         order_by="AnalysisEvent.seq")


class AnalysisEvent(Base):
    __tablename__ = "analysis_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    analysis: Mapped[Analysis] = relationship(back_populates="events")


class LearnedCategory(Base):
    """A market label that was confirmed for a kind of product (label + the tags that returned brands). Generic words only:
    no client names, brands or text. Shared by all users; the engine re-checks it with live data on every use."""
    __tablename__ = "learned_categories"
    __table_args__ = (UniqueConstraint("product_type", "label", name="uq_learned_type_label"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_type: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40), default="")
    label: Mapped[str] = mapped_column(String(60))
    tier: Mapped[str] = mapped_column(String(20), default="sector")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    hits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
