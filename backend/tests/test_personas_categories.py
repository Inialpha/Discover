"""Category-agnostic checks: toothpaste, skin cream, smartphone, fintech app, resume SaaS. Nothing here may depend on
phone vocabulary; competitor discovery, scoring and the report must behave for each."""

import asyncio
import json

import httpx
import pytest

from discover.personas import competitors as C
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
    assert "skincare" in C.search_terms(ProductIntake(**CASES["cream"]))
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


def test_related_brands_must_share_a_tag():
    assert C.shared_tags([{"id": "t1", "name": "Oral care"}], [{"id": "t1", "name": "Oral care"}, {"id": "t2", "name": "x"}]) == ["Oral care"]
    assert C.shared_tags([{"id": "t1"}], [{"id": "t9", "name": "y"}]) == []


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
