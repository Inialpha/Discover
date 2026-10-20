"""Baseline: users, analyses, analysis_events, learned_categories.

Databases created before Alembic was added already have these tables (the app used create_all), so each table is only
created when it is missing. Either way the database ends up at the same place.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "users" not in have:
        op.create_table(
            "users",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("name", sa.String(120), nullable=False, server_default=""),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if "analyses" not in have:
        op.create_table(
            "analyses",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("intake", sa.JSON(), nullable=False),
            sa.Column("options", sa.JSON(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("report_md", sa.Text(), nullable=True),
            sa.Column("summary", sa.JSON(), nullable=True),
            sa.Column("edits", sa.JSON(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_analyses_user_id", "analyses", ["user_id"])
        op.create_index("ix_analyses_status", "analyses", ["status"])
        op.create_index("ix_analyses_created_at", "analyses", ["created_at"])
    if "analysis_events" not in have:
        op.create_table(
            "analysis_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("analysis_id", sa.String(32), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("stage", sa.String(40), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_analysis_events_analysis_id", "analysis_events", ["analysis_id"])
    if "learned_categories" not in have:
        op.create_table(
            "learned_categories",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("product_type", sa.String(80), nullable=False),
            sa.Column("category", sa.String(40), nullable=False),
            sa.Column("label", sa.String(60), nullable=False),
            sa.Column("tier", sa.String(20), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("hits", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("product_type", "label", name="uq_learned_type_label"),
        )
        op.create_index("ix_learned_categories_product_type", "learned_categories", ["product_type"])


def downgrade() -> None:
    for t in ("learned_categories", "analysis_events", "analyses", "users"):
        op.drop_table(t)
