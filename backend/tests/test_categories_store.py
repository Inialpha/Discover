"""Learned categories: stored once confirmed, found again for the same product type, and an end-to-end run that uses the ladder."""

import asyncio
import json

import httpx
from sqlalchemy import select

from discover.api.db import Base, make_engine, make_session_factory
from discover.api.models import LearnedCategory
from discover.api.services import categories as C

TAGS = [{"id": "urn:tag:genre:brand:energy", "name": "Energy"}]


def run(coro):
    return asyncio.run(coro)


async def _db(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/c.db")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return eng, make_session_factory(eng)


def test_remember_then_known_for_exact_and_related_types(tmp_path):
    async def go():
        eng, sf = await _db(tmp_path)
        async with sf() as db:
            assert await C.remember(db, "Solar panel", "other", [{"label": "Energy", "tier": "sector", "tags": TAGS}]) == 1
            await C.remember(db, "solar panel", "other", [{"label": "energy", "tier": "sector", "tags": TAGS}])  # same mapping again: counted, not duplicated
            rows = (await db.execute(select(LearnedCategory))).scalars().all()
            assert len(rows) == 1 and rows[0].hits == 2 and rows[0].label == "energy"
            assert (await C.known_for(db, "solar panel", "other"))[0]["tags"] == TAGS
            assert (await C.known_for(db, "solar panels for homes", "other"))[0]["label"] == "energy"  # same category, shared word
            assert await C.known_for(db, "toothpaste", "beauty_personal_care") == []
            assert await C.remember(db, "x", "other", [{"label": "no tags", "tags": []}, {"label": "", "tags": TAGS}]) == 0
        await eng.dispose()
    run(go())


def test_api_run_with_the_ladder_stores_the_category_and_reuses_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from discover.api.main import create_app
    from tests.test_api import INTAKE, settings, signup, wait
    from tests.test_personas_step2 import LLM_SETTINGS
    from discover.engine.qloo.mock import make_transport

    monkeypatch.chdir(tmp_path)
    log: list[str] = []

    def llm(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        system, payload = body["messages"][0]["content"], json.loads(body["messages"][1]["content"])
        if system.startswith("You map a product"):
            log.append("map")
            out = {"need": "a phone that lasts", "labels": [{"label": "mobile phones", "tier": "alternative"}, {"label": "consumer electronics", "tier": "sector"}]}
        elif system.startswith("You judge whether brands"):
            log.append("fit")
            out = {"labels": {k: {"fit": "alternative", "keep": [b["name"] for b in v["brands"]][:3], "why": "same need"} for k, v in payload["labels"].items()}}
        elif "segment" in payload:
            out = {"segment_id": payload["segment"]["id"], "name": "Saver", "headline": "wants value", "who": "student"}
        else:
            out = {}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(out)}}]})

    intake = {**INTAKE, "competitors": [], "max_personas": 2}
    app = create_app(settings(database_url=f"sqlite:///{tmp_path}/e2e.db"),
                     engine_kwargs={"engine_settings": LLM_SETTINGS, "llm_transport": httpx.MockTransport(llm),
                                    # Qloo has no brand category for this product type, so the market map (the ladder) is what runs
                                    "qloo_transport": make_transport(lambda r: r.url.path == "/v2/tags" and r.url.params.get("filter.query") == "smartphone")})
    with TestClient(app) as c:
        h = signup(c)
        aid = c.post("/api/analyses", json={"intake": intake}, headers=h).json()["id"]
        assert wait(c, h, aid) == "complete"
        res = c.get(f"/api/analyses/{aid}", headers=h).json()["result"]
        m = res["market"]
        assert m["confirmed"] and m["need"] and (m["tiers"]["alternative"] or m["tiers"]["sector"])
        assert "Qloo" not in json.dumps(res["evidence_notes"]) and "LLM" not in json.dumps(res["evidence_notes"])
        first_maps = log.count("map")
        assert first_maps >= 1

        async def stored():
            from sqlalchemy import select
            async with app.state.session_factory() as db:
                return (await db.execute(select(LearnedCategory))).scalars().all()
        rows = c.portal.call(stored)
        assert rows and rows[0].tags and rows[0].product_type == "smartphone"
        aid2 = c.post("/api/analyses", json={"intake": intake}, headers=h).json()["id"]
        assert wait(c, h, aid2) == "complete"
        assert log.count("map") == first_maps  # the saved categories filled the market: no new map call
