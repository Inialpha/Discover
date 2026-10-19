"""The category ladder: market map -> Qloo tag test -> batched fit check -> ledger, for products with no direct competitors in Qloo."""

import json

import httpx

from discover.engine.modes.business.pipeline import Evidence
from discover.engine.personas import evidence as E
from discover.engine.personas import ladder as L
from discover.engine.personas.intake import ProductIntake
from discover.engine.qloo.client import QlooClient
from discover.engine.recorder import RunRecorder
from tests.test_personas_categories import _client
from tests.test_personas_step2 import run_async

SOLAR = ProductIntake(name="SunBox", product_type="solar panel", category="other", price=300000, currency="NGN", location="Lagos",
                      description="Rooftop solar panels with a battery for homes that lose grid power every day.")


def brand(i, name, tag, extra=()):
    return {"entity_id": f"B{i}", "name": name, "types": ["urn:entity:brand"], "tags": [{"id": tag, "name": tag.rsplit(":", 1)[-1]}, *extra]}


ENERGY = "urn:tag:genre:brand:energy"
ELEC = "urn:tag:genre:brand:electronics"
TAGS = {"solar panels": [], "home power equipment": [{"id": ELEC, "name": "Electronics", "type": "urn:tag:genre:brand"}],
        "energy": [{"id": ENERGY, "name": "Energy", "type": "urn:tag:genre:brand"}],
        "power generators": [{"id": ENERGY, "name": "Energy", "type": "urn:tag:genre:brand"}]}
BRANDS = {ENERGY: [brand(i, n, ENERGY) for i, n in enumerate(["Tesla Energy", "Honda Power", "Total", "Shell"], 1)],
          ELEC: [brand(i, n, ELEC) for i, n in enumerate(["LG", "Samsung", "Sony"], 10)]}


def qloo(req: httpx.Request) -> httpx.Response:
    p = req.url.params
    if req.url.path == "/v2/tags":
        return httpx.Response(200, json={"success": True, "results": {"tags": TAGS.get(p.get("filter.query"), [])}})
    if req.url.path == "/v2/insights":
        if "filter.tags" in p and p.get("filter.type") == "urn:entity:brand":
            return httpx.Response(200, json={"success": True, "results": {"entities": BRANDS.get(p["filter.tags"], [])}})
        return httpx.Response(200, json={"success": True, "results": {"demographics": []}})
    return httpx.Response(200, json={"success": True, "results": []})


class ScriptLLM:
    def __init__(self, maps, fit):
        self.maps, self.fit, self.log = list(maps), fit, []

    async def chat_json(self, name, system, user, **kw):
        self.log.append((name, json.loads(user)))
        if name == "market_map":
            return self.maps.pop(0)
        if name == "ladder_fit_check":
            return self.fit(json.loads(user))
        return {}


def fit_energy(payload):
    out = {}
    for label, v in payload["labels"].items():
        names = [b["name"] for b in v["brands"]]
        out[label] = ({"fit": "none", "keep": [], "why": "general electronics"} if "LG" in names
                      else {"fit": "alternative", "keep": names[:3], "why": "other ways to get power"})
    return {"labels": out}


def run(llm, direct=(), known=None, tmp_path=None):
    async def go():
        async with _client(tmp_path, httpx.MockTransport(qloo)) as c:
            return await L.run_ladder(c, SOLAR, Evidence(), llm, list(direct), known=known)
    return run_async(go())


MAP1 = {"need": "keep the lights on without the grid", "labels": [
    {"label": "solar panels", "tier": "direct"}, {"label": "home power equipment", "tier": "alternative"},
    {"label": "energy", "tier": "sector"}, {"label": "power generators", "tier": "alternative"}]}


def test_ladder_rejects_wrong_market_and_keeps_confirmed_brands(tmp_path):
    llm = ScriptLLM([MAP1], fit_energy)
    r = run(llm, tmp_path=tmp_path)
    names = [b["name"] for b in r["kept"]]
    assert r["confirmed"] and names and "LG" not in names and all(b["tier"] == "alternative" for b in r["kept"])
    ledger = {e["label"]: e for e in r["ledger"]}
    assert "no matching" in ledger["solar panels"]["result"]
    assert "rejected" in ledger["home power equipment"]["result"] and ledger["home power equipment"]["returned"][0] == "LG"
    assert [n for n, _ in llm.log].count("market_map") == 1 and [n for n, _ in llm.log].count("ladder_fit_check") == 1  # two LLM calls
    assert r["learned"] and r["learned"][0]["tags"][0]["id"] == ENERGY


def test_second_round_is_told_what_failed_and_never_repeats_labels(tmp_path):
    first = {"need": "power", "labels": [{"label": "solar panels", "tier": "direct"}, {"label": "home power equipment", "tier": "alternative"}]}
    second = {"need": "power", "labels": [{"label": "solar panels", "tier": "direct"}, {"label": "energy", "tier": "sector"}]}
    llm = ScriptLLM([first, second], fit_energy)
    r = run(llm, tmp_path=tmp_path)
    maps = [p for n, p in llm.log if n == "market_map"]
    assert len(maps) == 2 and {t["label"] for t in maps[1]["tried"]} == {"solar panels", "home power equipment"}
    assert [e["label"] for e in r["ledger"]] == ["solar panels", "home power equipment", "energy"]  # the repeat was dropped
    assert r["confirmed"]


def test_stops_after_max_rounds_and_says_nothing_was_confirmed(tmp_path):
    empty = {"need": "x", "labels": [{"label": "unknown thing", "tier": "direct"}]}
    llm = ScriptLLM([empty, {"need": "x", "labels": [{"label": "another unknown", "tier": "sector"}]}, empty], fit_energy)
    r = run(llm, tmp_path=tmp_path)
    assert not r["confirmed"] and r["kept"] == [] and len(llm.maps) == 1  # two rounds used, third never asked
    assert any("could be confirmed" in n for n in r["notes"])


def test_known_mappings_skip_the_map_call_when_they_fill_the_market(tmp_path):
    known = [{"label": "energy", "tier": "alternative", "tags": [{"id": ENERGY, "name": "Energy"}]}]
    llm = ScriptLLM([], fit_energy)
    r = run(llm, known=known, tmp_path=tmp_path)
    assert r["confirmed"] and [n for n, _ in llm.log] == ["ladder_fit_check"]


def test_direct_competitors_known_asks_only_for_other_tiers(tmp_path):
    llm = ScriptLLM([MAP1], fit_energy)
    r = run(llm, direct=[{"entity_id": "D1"}, {"entity_id": "D2"}], tmp_path=tmp_path)
    assert "already known" in llm.log[0][1]["note"] and all(e["tier"] != "direct" for e in r["ledger"] if e["tier"])


def test_clean_labels_drops_junk_duplicates_and_tried():
    need, out = L.clean_labels({"need": "n", "labels": [{"label": "Energy", "tier": "sector"}, {"label": "energy", "tier": "sector"},
                                                       {"label": "<script>", "tier": "x"}, {"label": "a", "tier": "x"},
                                                       {"label": "oral care", "tier": "weird"}, "junk", {"label": "tried one"}]}, {"tried one"})
    assert [o["label"] for o in out] == ["energy", "oral care"] and out[1]["tier"] == "sector"


def test_resolve_and_skew_reports_the_market_and_uses_alternatives_as_standins(tmp_path):
    llm = ScriptLLM([MAP1], fit_energy)
    async def go():
        async with _client(tmp_path, httpx.MockTransport(qloo)) as c:
            return await E.resolve_and_skew(c, SOLAR, llm=llm, discover=True)
    r = run_async(go())
    m = r["market"]
    assert m["confirmed"] and m["need"] and m["tiers"]["alternative"] and not m["tiers"]["direct"]
    assert r["anchors"] and all(a["tier"] == "alternative" for a in r["anchors"]) and r["learned"]
