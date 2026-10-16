"""Category-agnostic checks: toothpaste, skin cream, smartphone, fintech app, resume SaaS. Nothing here may depend on
phone vocabulary; competitor discovery, scoring and the report must behave for each."""

import asyncio
import json

import httpx
import pytest

from discover.personas import competitors as C
from discover.qloo import calls
from discover.personas import evidence as E
from discover.personas.affordability import assess
from discover.personas.intake import ProductIntake
from discover.personas.runner import PersonaOptions, execute_personas
from discover.personas.scoring import score_segments
from discover.qloo.client import QlooClient
from discover.qloo.mock import make_transport
from discover.recorder import RunRecorder
from tests.test_personas_step2 import LLM_SETTINGS, QLOO_SETTINGS, run_async

CASES = {
    "toothpaste": dict(name="BrightSmile", product_type="toothpaste", category="beauty_personal_care", price=1500, currency="NGN",
                       location="Lagos", purchase_type="repeat", purchases_per_year=12,
                       description="Fluoride toothpaste for daily family use at an affordable price."),
    "cream": dict(name="GlowSkin", product_type="skin cream", category="beauty_personal_care", price=8000, currency="NGN",
                  location="Lagos", purchase_type="repeat", purchases_per_year=4,
                  description="A moisturising face cream for dry skin with shea butter."),
    "phone": dict(name="Zip 5", product_type="smartphone", category="smartphone", price=40000, currency="NGN", location="Lagos",
                  description="A budget smartphone with a large battery for everyday use."),
    "fintech": dict(name="PayFlow", product_type="payments app", category="fintech_app", price=0, currency="USD", location="New York",
                    description="A free app for splitting bills and sending money to friends."),
    "resume": dict(name="CVForge", product_type="resume builder", category="software_saas", price=9, currency="USD",
                   location="New York", purchase_type="monthly",
                   description="Generates a resume and cover letter from a job description."),
}


@pytest.fixture(params=sorted(CASES))
def case(request):
    return request.param, ProductIntake(**CASES[request.param])


def test_every_case_is_valid_and_assessed(case, store):
    _, i = case
    assert i.validate() == []
    aff = assess(i, store)
    assert aff.tier in ("budget", "mass", "upper", "premium")


def test_every_case_gets_ranked_segments(case, store):
    _, i = case
    res = score_segments(i, assess(i, store))
    assert res.ranked, "no segment fits this category and tier"


def test_resume_product_surfaces_job_seekers(store):
    i = ProductIntake(**CASES["resume"])
    ids = [s.id for s in score_segments(i, assess(i, store)).ranked]
    assert "job_seekers" in ids


def test_search_terms_use_product_type_then_category_defaults():
    assert C.search_terms(ProductIntake(**CASES["toothpaste"]))[0] == "toothpaste"
    assert C.search_terms(ProductIntake(**CASES["cream"])) == ["skin cream"]  # own words only: defaults mislead
    d = dict(CASES["phone"]); d["product_type"] = ""
    assert C.search_terms(ProductIntake(**d)) == ["smartphone", "mobile phone"]


@pytest.mark.parametrize("tag,term,ok", [("Toothpaste", "toothpaste", True), ("Skin Creams", "skin cream", True),
                                          ("Skin Care", "skin cream", False), ("Toothbrush", "toothpaste", False),
                                          ("Resume Builders", "resume builder", True)])
def test_tag_matches(tag, term, ok):
    assert C.tag_matches(tag, term) is ok


def test_clean_llm_names():
    assert C.clean_llm_names({"brands": ["Colgate", " colgate ", "Oral-B", 5, "x", "Sensodyne<script>"]}) == ["Colgate", "Oral-B"]
    assert C.clean_llm_names("garbage") == [] and C.clean_llm_names(None) == []


def _client(tmp_path, transport=None):
    return QlooClient(QLOO_SETTINGS, RunRecorder(tmp_path / "run"), transport=transport or make_transport(), synthetic=True)


def test_discovery_finds_competitors_through_qloo_tags(tmp_path):
    i = ProductIntake(**CASES["toothpaste"])
    async def go():
        async with _client(tmp_path) as c:
            return await E.resolve_and_skew(c, i, discover=True)
    r = run_async(go())
    assert r["anchors"] and {a["source"] for a in r["anchors"]} == {"qloo_tag"} and len(r["anchors"]) <= 5
    assert r["age_index"]


def test_given_competitors_come_first_and_are_labelled(tmp_path):
    i = ProductIntake(**CASES["cream"], competitors=["Nivea"])
    async def go():
        async with _client(tmp_path) as c:
            return await E.resolve_and_skew(c, i, discover=True)
    r = run_async(go())
    assert r["anchors"][0]["source"] == "given" and r["anchors"][0]["query"] == "Nivea"


def test_discovery_off_uses_only_given(tmp_path):
    i = ProductIntake(**CASES["cream"], competitors=["Nivea"])
    async def go():
        async with _client(tmp_path) as c:
            r = await E.resolve_and_skew(c, i, discover=False)
            return r, c.calls_used
    r, used = run_async(go())
    assert [a["source"] for a in r["anchors"]] == ["given"] and used >= 1


class FakeLLM:
    def __init__(self, names): self.names, self.calls = names, 0
    async def chat_json(self, name, system, user, **kw):
        self.calls += 1
        return {"brands": self.names}


def test_llm_suggestions_are_kept_only_when_qloo_confirms(tmp_path):
    def search_handler(req):  # Qloo knows Colgate but not Zorblax
        if req.url.path == "/search":
            term = req.url.params.get("query", "")
            res = [{"entity_id": "ID1", "name": "Colgate", "types": ["urn:entity:brand"], "tags": []}] if term == "Colgate" else []
            return httpx.Response(200, json={"success": True, "results": res})
        return httpx.Response(400, json={"success": False})
    i = ProductIntake(**CASES["toothpaste"])
    llm = FakeLLM(["Colgate", "Zorblax"])
    async def go():
        async with _client(tmp_path, httpx.MockTransport(search_handler)) as c:
            return await E.resolve_and_skew(c, i, llm=llm, discover=True)
    r = run_async(go())
    assert [a["name"] for a in r["anchors"]] == ["Colgate"] and r["anchors"][0]["source"] == "llm_confirmed"
    assert any("Zorblax" in n for n in r["notes"]) and llm.calls == 1


def test_no_competitor_anywhere_degrades_to_rules_with_a_note(tmp_path):
    i = ProductIntake(**CASES["cream"])
    async def go():
        async with _client(tmp_path, make_transport(lambda r: True)) as c:
            return await E.resolve_and_skew(c, i, discover=True)
    r = run_async(go())
    assert r["anchors"] == [] and r["age_index"] == {} and any("No competitor" in n for n in r["notes"])


@pytest.mark.parametrize("key", sorted(CASES))
def test_runner_end_to_end_per_category(key, store, tmp_path):
    i = ProductIntake(**CASES[key], max_personas=3)
    code, run, summary = run_async(execute_personas(PersonaOptions(intake=i, out=tmp_path / "runs", mock=True, zip=False), QLOO_SETTINGS, store))
    res = json.loads((run / "04_personas.json").read_text())
    md = (run / "04_personas.md").read_text()
    assert code == 0 and len(res["personas"]) == 3
    assert "Competitors used" in md and "Qloo brands for the product's tag" in md
    low = md.lower()
    if key != "phone":
        assert "battery" not in low and "smartphone" not in low


def test_feature_words_flag_category_claims(store):
    from discover.personas.writer import screen_claim
    i = ProductIntake(**CASES["toothpaste"])
    assert screen_claim("Fluoride protection for daily use", i)[1] == []  # stated in the product text
    assert "whitening" in screen_claim("Whitening that lasts", i)[1]
    j = ProductIntake(**CASES["cream"])
    assert "fragrance" in screen_claim("A light fragrance you will love", j)[1]


# ---- regression tests from the live runs of 2026-10-14 ---------------------------------------------------------
REAL_PHONE_TAGS = [{"id": "urn:tag:category:place:mobile_phone", "name": "Mobile phone"},
                   {"id": "urn:tag:category:place:mobile_phone_repair_shop", "name": "Mobile phone repair shop"}]
REAL_SKIN_TAGS = [{"id": "urn:tag:genre:brand:health_and_beauty:skincare", "name": "Skincare"},
                  {"id": "urn:tag:category:place:skin_care", "name": "Skin care"}]


def test_place_category_tags_are_not_brand_tags():
    assert not any(C.is_brand_tag(t) for t in REAL_PHONE_TAGS)  # live run: these returned banks as phone competitors
    assert [t["name"] for t in REAL_SKIN_TAGS if C.is_brand_tag(t)] == ["Skincare"]


def _brand(eid, *tags):
    """tags are real-shaped ids, e.g. 'genre:brand:health_and_beauty' or 'aesthetic_property:qloo:clean'."""
    return {"entity_id": eid, "name": eid, "tags": [{"id": f"urn:tag:{t}", "name": t, "type": "urn:tag:" + ":".join(t.split(":")[:2])}
                                                     for t in tags]}


def test_coherent_brands_keeps_a_real_cluster():
    ents = [_brand("Milani", "genre:brand:health_and_beauty"), _brand("Sigma", "genre:brand:health_and_beauty:skincare"),
            _brand("BH", "genre:brand:health_and_beauty"), _brand("Bank", "genre:brand:financial_services")]
    assert [e["entity_id"] for e in C.coherent_brands(ents)] == ["Milani", "Sigma", "BH"]


def test_coherent_brands_rejects_a_grab_bag():
    # live run: a bank, a fashion designer, a make-up artist, a shop: location favourites, not competitors
    ents = [_brand("GTBank", "genre:brand:financial_services"), _brand("Kunbi", "genre:brand:fashion"),
            _brand("Banke", "genre:brand:health_and_beauty"), _brand("Habari", "genre:brand:retail")]
    assert C.coherent_brands(ents) == []


def test_style_tags_do_not_make_a_bank_a_soap_peer():
    pears = [_brand("Pears", "genre:brand:health_and_beauty", "aesthetic_property:qloo:clean")]
    bank = [_brand("Wema", "genre:brand:financial_services", "aesthetic_property:qloo:clean")]
    assert C.genre_closeness(pears[0]["tags"], bank[0]["tags"]) == 0  # live run: Wema Bank was kept for sharing 'Clean'


def test_genre_closeness_counts_shared_depth():
    a = _brand("a", "genre:brand:wine_and_spirits:beer")["tags"]
    assert C.genre_closeness(a, _brand("b", "genre:brand:wine_and_spirits")["tags"]) == 1
    assert C.genre_closeness(a, _brand("c", "genre:brand:wine_and_spirits:beer:other")["tags"]) == 2
    assert C.genre_closeness(a, _brand("d", "genre:brand:retail")["tags"]) == 0


def test_two_given_competitors_skip_discovery_calls(tmp_path):
    i = ProductIntake(**CASES["cream"], competitors=["Nivea", "Vaseline"])
    async def go():
        async with _client(tmp_path) as c:
            r = await E.resolve_and_skew(c, i, discover=True)
            return r, [x.spec.path for x in c.results]
    r, paths = run_async(go())
    assert [a["source"] for a in r["anchors"]][:2] == ["given", "given"] and "/v2/tags" not in paths


def test_tag_route_rejected_when_only_place_tags_exist(tmp_path):
    def handler(req):
        if req.url.path == "/v2/tags":
            return httpx.Response(200, json={"success": True, "results": {"tags": REAL_PHONE_TAGS}})
        if req.url.path == "/search":
            return httpx.Response(200, json={"success": True, "results": []})
        return httpx.Response(400, json={"success": False})
    i = ProductIntake(**CASES["phone"])
    async def go():
        async with _client(tmp_path, httpx.MockTransport(handler)) as c:
            return await E.resolve_and_skew(c, i, discover=True)
    r = run_async(go())
    assert r["anchors"] == [] and any("no brand category" in n.lower() for n in r["notes"])


# ---- category route from live probe (2026-10-14): hard filter works, anchors' own tags name the category -------
def _anchor(name, *tag_ids):
    return {"entity_id": name, "name": name, "tags": [{"id": f"urn:tag:{t}", "name": t, "type": "urn:tag:genre:brand"} for t in tag_ids]}


def test_category_candidates_prefers_deepest_shared_category():
    a = [_anchor("Nivea", "genre:brand:health_and_beauty", "genre:brand:health_and_beauty:skincare"),
         _anchor("Vaseline", "genre:brand:health_and_beauty:skincare")]
    ids = [c["id"] for c in C.category_candidates(a)]
    assert ids[0] == "urn:tag:genre:brand:health_and_beauty:skincare" and "urn:tag:genre:brand:health_and_beauty" in ids


def test_category_candidates_ignores_style_tags_and_minority_categories():
    a = [_anchor("Tecno", "genre:brand:electronics:phones_and_tablets", "aesthetic_property:qloo:clean"),
         _anchor("Infinix", "genre:brand:electronics:phones_and_tablets"), _anchor("Odd", "genre:brand:retail")]
    ids = [c["id"] for c in C.category_candidates(a)]
    assert "urn:tag:genre:brand:retail" not in ids and ids[0].endswith("electronics:phones_and_tablets")


def _category_handler(local_empty=False):
    def handler(req):
        p, q = req.url.path, dict(req.url.params)
        if p == "/search":
            n = q["query"]
            tags = [{"id": "urn:tag:genre:brand:health_and_beauty:skincare", "name": "Skincare", "type": "urn:tag:genre:brand"}]
            return httpx.Response(200, json={"results": [{"entity_id": n, "name": n, "types": ["urn:entity:brand"], "tags": tags}]})
        if p == "/v2/insights" and q.get("filter.type") == "urn:entity:brand" and q.get("filter.tags"):
            if local_empty and ("signal.location.query" in q or "filter.location.query" in q):
                return httpx.Response(200, json={"results": {"entities": []}})
            tag = {"id": q["filter.tags"], "name": "Skincare", "type": "urn:tag:genre:brand"}
            return httpx.Response(200, json={"results": {"entities": [
                {"entity_id": f"P{i}", "name": f"Peer{i}", "tags": [tag]} for i in range(4)]}})
        if p == "/v2/insights" and q.get("filter.type") == "urn:demographics":
            return httpx.Response(200, json={"results": {"demographics": [{"query": {"age": {"25_to_29": 0.3}, "gender": {"male": 0.1}}}]}})
        return httpx.Response(404, json={})
    return handler


def test_category_peers_fill_in_from_the_anchors_own_category(tmp_path):
    i = ProductIntake(**CASES["cream"], competitors=["Nivea", "Vaseline"])
    async def go():
        async with _client(tmp_path, httpx.MockTransport(_category_handler())) as c:
            return await E.resolve_and_skew(c, i, discover=True)
    r = run_async(go())
    names = [(a["name"], a["source"]) for a in r["anchors"]]
    assert names[:2] == [("Nivea", "given"), ("Vaseline", "given")] and all(s == "qloo_category" for _, s in names[2:]) and len(names) == 5
    assert r["category"]["id"] == "urn:tag:genre:brand:health_and_beauty:skincare" and r["category"]["scope"] == "local"
    assert r["category"]["added"] is True


def test_category_peers_fall_back_to_global_with_a_note(tmp_path):
    i = ProductIntake(**CASES["cream"], competitors=["Nivea", "Vaseline"])
    async def go():
        async with _client(tmp_path, httpx.MockTransport(_category_handler(local_empty=True))) as c:
            return await E.resolve_and_skew(c, i, discover=True)
    r = run_async(go())
    assert r["category"]["scope"] == "global" and any("outside the location" in n for n in r["notes"])


def _broad_handler(record_tags=True):
    def handler(req):
        p, q = req.url.path, dict(req.url.params)
        if p == "/search":
            n = q["query"]
            return httpx.Response(200, json={"results": [{"entity_id": n, "name": n, "types": ["urn:entity:brand"], "tags": [
                {"id": "urn:tag:genre:brand:health_and_beauty", "name": "Health & Beauty", "type": "urn:tag:genre:brand"}]}]})
        if p == "/entities":
            tags = [{"id": "urn:tag:competitor_brand:qloo:sensodyne", "name": "Sensodyne", "type": "urn:tag:competitor_brand:qloo"},
                    {"id": "urn:tag:similar_brand:qloo:crest", "name": "Crest", "type": "urn:tag:similar_brand:qloo"},
                    {"id": "urn:tag:industry:qloo:oral_care", "name": "Oral care", "type": "urn:tag:industry:qloo"}] if record_tags else []
            return httpx.Response(200, json={"results": [{"name": "x", "tags": tags}]})
        if p == "/v2/insights" and q.get("filter.tags"):
            tag = {"id": q["filter.tags"], "name": "H&B", "type": "urn:tag:genre:brand"}
            if "signal.interests.entities" not in q:  # category alone is broad: salons
                return httpx.Response(200, json={"results": {"entities": [{"entity_id": f"H{i}", "name": f"Salon{i}", "tags": [tag]} for i in range(4)]}})
            return httpx.Response(200, json={"results": {"entities": [{"entity_id": f"P{i}", "name": f"Peer{i}", "tags": [tag]} for i in range(4)]}})
        if p == "/v2/insights" and q.get("filter.type") == "urn:demographics":
            return httpx.Response(200, json={"results": {"demographics": [{"query": {"age": {"25_to_29": 0.3}, "gender": {"male": 0.1}}}]}})
        return httpx.Response(404, json={})
    return handler


def test_category_alone_never_adds_competitors(tmp_path):
    i = ProductIntake(**CASES["toothpaste"], competitors=["Colgate", "Pepsodent"])
    async def go():
        async with _client(tmp_path, httpx.MockTransport(_broad_handler(record_tags=False))) as c:
            return await E.resolve_and_skew(c, i, discover=True)
    r = run_async(go())
    names = [a["name"] for a in r["anchors"]]
    assert not any(n.startswith("Salon") for n in names)  # live run: hair salons and make-up artists
    assert {a["source"] for a in r["anchors"] if a["name"].startswith("Peer")} <= {"qloo_category"}


def test_competitor_tags_on_brand_records_are_confirmed_before_use(tmp_path):
    i = ProductIntake(**CASES["toothpaste"], competitors=["Colgate"])
    async def go():
        async with _client(tmp_path, httpx.MockTransport(_broad_handler())) as c:
            return await E.resolve_and_skew(c, i, discover=True, want=5)
    r = run_async(go())
    got = {a["name"]: a["source"] for a in r["anchors"]}
    assert got["Sensodyne"] == "qloo_competitor_tags" and got["Crest"] == "qloo_competitor_tags"
    assert r["profiles"]["Colgate"]["industries"] == ["Oral care"]


def test_profile_from_extras_reads_competitor_and_segment_tags():
    from discover.personas import competitors as C
    pr = C.profile_from_extras({"tags": [
        {"id": "urn:tag:competitor_brand:qloo:infinix", "name": None},
        {"id": "urn:tag:customer_segment:qloo:budget_conscious", "name": "Budget conscious"},
        {"id": "urn:tag:competitor_brand:qloo", "name": "x"}]})
    assert pr["competitors"] == ["infinix"] and pr["segments"] == ["Budget conscious"]


def test_entity_extras_finds_competitive_set_wherever_it_sits():
    from discover.qloo import normalize as nz
    body = {"results": {"entities": [{"properties": {"competitive_set": ["A", "B"], "complementary_brands": ["C"]},
                                      "tags": [{"id": "urn:tag:genre:brand:x", "name": "X", "type": "urn:tag:genre:brand"}]}]}}
    e = nz.entity_extras(body)
    assert e["competitive_set"] == ["A", "B"] and e["complementary_brands"] == ["C"] and e["tags"][0]["id"].endswith("brand:x")
    assert nz.entity_extras(None)["competitive_set"] == []


def test_semantic_search_variant_comes_first_with_plain_fallback():
    s = calls.tags_of_type("t", "urn:tag:genre:brand", query="toothpaste", semantic=True)
    assert s.variants[0].params["feature.semantic_search"] == "true" and "feature.semantic_search" not in s.variants[1].params
