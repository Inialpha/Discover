"""Alembic: a new database, an old database with data, and no drift between models.py and the migrations."""

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from discover.api import migrations
from discover.api.db import Base


def engine(tmp_path):
    return sa.create_engine(f"sqlite:///{tmp_path}/m.db")


def upgrade(eng, rev="head"):
    with eng.begin() as conn:
        migrations.command.upgrade(migrations.config(conn), rev)


def test_new_database_gets_every_table_and_matches_the_models(tmp_path):
    eng = engine(tmp_path)
    upgrade(eng)
    names = set(sa.inspect(eng).get_table_names())
    assert {"users", "analyses", "analysis_events", "learned_categories", "products", "alembic_version"} <= names
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": False}), Base.metadata)
    assert diff == [], f"models.py and the migrations disagree: {diff}"  # add a migration when you change models.py


def test_upgrade_is_repeatable(tmp_path):
    eng = engine(tmp_path)
    upgrade(eng)
    upgrade(eng)  # already at head: nothing happens, nothing breaks


def test_old_database_keeps_its_data_and_gets_products(tmp_path):
    eng = engine(tmp_path)
    upgrade(eng, "0001")  # the schema as it was before products
    now = datetime.now(timezone.utc)
    with eng.begin() as conn:
        conn.execute(sa.text("insert into users (id,email,name,password_hash,created_at) values ('u1','a@b.c','A','x',:t)"), {"t": now})
        for i, name in enumerate(["Zip 5", "GlowSkin"]):
            conn.execute(sa.text("insert into analyses (id,user_id,title,status,intake,options,edits,created_at) "
                                 "values (:i,'u1','t','complete',:intake,'{}','{}',:t)"),
                         {"i": f"a{i}", "intake": json.dumps({"name": name}), "t": now})
    upgrade(eng)
    with eng.connect() as conn:
        rows = conn.execute(sa.text("select a.id, a.run_number, a.product_id, p.name, p.user_id from analyses a join products p on p.id = a.product_id order by a.id")).fetchall()
    assert [(r[0], r[1], r[3], r[4]) for r in rows] == [("a0", 1, "Zip 5", "u1"), ("a1", 1, "GlowSkin", "u1")]
    assert rows[0][2] != rows[1][2]  # each old analysis got a product of its own


def test_database_created_by_the_old_create_all_is_adopted(tmp_path):
    eng = engine(tmp_path)
    with eng.begin() as conn:  # what the app did before Alembic: tables exist, no alembic_version, no product columns
        for t in ("users", "analyses", "analysis_events", "learned_categories"):
            Base.metadata.tables[t].create(conn, checkfirst=True) if t != "analyses" else None
        conn.execute(sa.text("create table analyses (id varchar(32) primary key, user_id varchar(32), title varchar(200), status varchar(20), "
                             "intake json, options json, result json, report_md text, summary json, edits json, error text, created_at datetime, finished_at datetime)"))
    upgrade(eng)
    cols = {c["name"] for c in sa.inspect(eng).get_columns("analyses")}
    assert {"product_id", "run_number", "changes"} <= cols and "products" in sa.inspect(eng).get_table_names()
