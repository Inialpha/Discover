"""Products: a parent that groups the runs (analyses) of one product.

Adds the products table and, on analyses: product_id (the link to the parent), run_number and changes (what differed from the
previous run). Every existing analysis becomes run 1 of its own new product, so nothing is lost.

Revision ID: 0002
Revises: 0001
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "products" not in insp.get_table_names():
        op.create_table(
            "products",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_products_user_id", "products", ["user_id"])
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("analyses")}
    with op.batch_alter_table("analyses") as b:
        if "product_id" not in cols:
            b.add_column(sa.Column("product_id", sa.String(32), nullable=True))
            b.create_index("ix_analyses_product_id", ["product_id"])
            b.create_foreign_key("fk_analyses_product_id", "products", ["product_id"], ["id"], ondelete="CASCADE")
        if "run_number" not in cols:
            b.add_column(sa.Column("run_number", sa.Integer(), nullable=False, server_default="1"))
        if "changes" not in cols:
            b.add_column(sa.Column("changes", sa.JSON(), nullable=True))
    # each analysis that has no product yet becomes run 1 of a product of its own
    bind = op.get_bind()
    analyses = sa.table("analyses", sa.column("id"), sa.column("user_id"), sa.column("intake", sa.JSON()), sa.column("created_at"),
                        sa.column("product_id"), sa.column("run_number"), sa.column("changes", sa.JSON()))
    products = sa.table("products", sa.column("id"), sa.column("user_id"), sa.column("name"), sa.column("created_at"), sa.column("updated_at"))
    rows = bind.execute(sa.select(analyses.c.id, analyses.c.user_id, analyses.c.intake, analyses.c.created_at)
                        .where(analyses.c.product_id.is_(None))).fetchall()
    for aid, uid, intake, created in rows:
        pid = uuid.uuid4().hex
        name = ((intake or {}).get("name") or "Untitled product")[:120] if isinstance(intake, dict) else "Untitled product"
        bind.execute(products.insert().values(id=pid, user_id=uid, name=name, created_at=created, updated_at=created))
        bind.execute(analyses.update().where(analyses.c.id == aid).values(product_id=pid, run_number=1, changes=[]))


def downgrade() -> None:
    with op.batch_alter_table("analyses") as b:
        b.drop_constraint("fk_analyses_product_id", type_="foreignkey")
        b.drop_index("ix_analyses_product_id")
        b.drop_column("changes")
        b.drop_column("run_number")
        b.drop_column("product_id")
    op.drop_table("products")
