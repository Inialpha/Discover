"""Lean competitor discovery: the LLM only chooses among brands Qloo returned, and identity is checked before peers are fetched."""

import asyncio
import json

import httpx

from discover.engine.modes.business.pipeline import Evidence
from discover.engine.personas import lean as L
from discover.engine.personas.evidence import pick_anchor
from discover.engine.personas.intake import ProductIntake
from tests.test_personas_categories import CASES, _client

HB = {"id": "urn:tag:genre:brand:health_and_beauty", "name": "Health & Beauty", "type": "urn:tag:genre:brand"}
FIN = {"id": "urn:tag:genre:brand:finance", "name": "Finance", "type": "urn:tag:genre:brand"}


def run(coro):
    return asyncio.run(coro)


def peer(i, name, tag, about):
    return {"entity_id": f"P{i}", "name": name, "type": "urn:entity", "subtype": "urn:entity:brand", "tags": [tag],
            "properties": {"short_description": about, "audience_identity": f"People who use {name}."}}


PEERS = [peer(1, "Oral-B", HB, "Toothbrushes and oral care."), peer(2, "Sensodyne", HB, "Sensitive teeth toothpaste."),
         peer(3, "Crest", HB, "Toothpaste and mouthwash."), peer(4, "GTBank", FIN, "A Nigerian bank."), peer(5, "Fidelity", FIN, "A bank.")]


def qloo(seen):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.path, dict(req.url.params)))
        if req.url.path == "/search":
            q = req.url.params.get("query", "")
            tags = [HB]
            res = [{"entity_id": f"G-{q}", "name": q, "types": ["urn:entity:brand"], "tags": tags,
                    "disambiguation": "university" if q == "Colgate" else ""}] if q in ("Colgate", "Pepsodent") else []
            return httpx.Response(200, json={"success": True, "results": res})
        if req.url.path == "/v2/insights":
            return httpx.Response(200, json={"success": True, "results": {"entities": PEERS}})
        return httpx.Response(400, json={"success": False})
    return httpx.MockTransport(handler)


class LLM:
    def __init__(self, verify=None, similar=None, fail=False):
        self.verify, self.similar, self.fail, self.names = verify or {}, similar, fail, []

    async def chat_json(self, name, system, user, **kw):
        self.names.append(name)
        if self.fail:
            raise RuntimeError("down")
        if name == "verify_competitor_identity":
            return {"matches": self.verify}
        if name == "select_similar_brands":
            self.cards = json.loads(user)["candidates"]
            return {"similar": self.similar}
        return {}


def go(tmp_path, llm, comps=("Colgate", "Pepsodent")):
    i = ProductIntake(**CASES["toothpaste"], competitors=list(comps))
    seen: list = []

    async def inner():
        async with _client(tmp_path, qloo(seen)) as c:
            ev = Evidence()
            return await L.discover_lean(c, i, ev, pick_anchor, llm=llm), ev
    r, ev = run(inner())
    return r, ev, seen


def test_llm_picks_among_returned_brands_and_unknown_ids_are_ignored(tmp_path):
    llm = LLM(verify={"Colgate": True, "Pepsodent": True}, similar=["P3", "BOGUS", "P2", "P3"])
    r, ev, seen = go(tmp_path, llm)
    names = [(a["name"], a["source"]) for a in r["anchors"]]
    assert names == [("Colgate", "given"), ("Pepsodent", "given"), ("Crest", "qloo_similar"), ("Sensodyne", "qloo_similar")]
    assert [p for p, _ in seen].count("/search") == 2 and [p for p, _ in seen].count("/v2/insights") == 1  # 3 Qloo calls in all
    assert llm.names == ["verify_competitor_identity", "select_similar_brands"]
    assert all(set(c) == {"id", "name", "about", "tags"} for c in llm.cards)  # the LLM sees ids, names, a line and tags only
    market = [e for e in ev.items if e["segment"] == "Market"]
    assert market and market[0]["data"]["anchored"] and [e["name"] for e in market[0]["data"]["entities"]] == ["Crest", "Sensodyne"]
    insights = next(q for p, q in seen if p == "/v2/insights")
    assert insights["filter.tags"] == HB["id"] and "signal.interests.entities" in insights and "G-Colgate" in insights["signal.interests.entities"]


def test_wrong_entity_is_dropped_before_its_peers_are_fetched(tmp_path):
    llm = LLM(verify={"Colgate": False, "Pepsodent": False}, similar=["P1"])
    r, ev, seen = go(tmp_path, llm)
    assert r["anchors"] == [] and set(r["unresolved"]) == {"Colgate", "Pepsodent"}
    assert not [p for p, _ in seen if p == "/v2/insights"] and "select_similar_brands" not in llm.names


def test_without_an_llm_brands_in_the_competitors_category_are_used(tmp_path):
    r, ev, seen = go(tmp_path, None)
    picked = [a["name"] for a in r["anchors"] if a["source"] == "qloo_similar"]
    assert picked == ["Oral-B", "Sensodyne", "Crest"] and "GTBank" not in picked


def test_llm_failure_falls_back_the_same_way(tmp_path):
    r, ev, seen = go(tmp_path, LLM(fail=True))
    assert [a["name"] for a in r["anchors"] if a["source"] == "qloo_similar"] == ["Oral-B", "Sensodyne", "Crest"]


def test_select_similar_edge_cases():
    i = ProductIntake(**CASES["toothpaste"])
    cands = [{"entity_id": "A", "name": "A", "tags": []}]
    assert run(L.select_similar(None, i, cands, 3)) is None
    assert run(L.select_similar(LLM(similar=["A"]), i, [], 3)) is None
    assert run(L.select_similar(LLM(similar="nope"), i, cands, 3)) is None
    assert run(L.select_similar(LLM(similar=["A"]), i, cands, 0)) is None
    assert run(L.select_similar(LLM(similar=[]), i, cands, 3)) == []


def test_card_is_short():
    c = L.card({"entity_id": "X", "name": "N", "properties": {"short_description": "w " * 200},
                "tags": [{"id": "urn:tag:genre:brand:a", "name": "A"}, {"id": "urn:tag:style:x", "name": "Style"}] + [{"id": f"urn:tag:genre:brand:{n}", "name": n} for n in "bcd"]})
    assert len(c["about"]) <= 110 and c["tags"] == ["A", "b", "c"]
