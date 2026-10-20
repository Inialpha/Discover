import asyncio
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from discover.engine.cli import main
from discover.config import Settings
from discover.engine.llm.client import LLMClient
from discover.engine.personas import evidence as E
from discover.engine.personas import writer as W
from discover.engine.personas.affordability import assess
from discover.engine.personas.runner import PersonaOptions, execute_personas
from discover.engine.personas.scoring import score_segments
from discover.engine.qloo.client import QlooClient
from discover.engine.qloo.mock import make_transport
from discover.engine.recorder import RunRecorder

LLM_SETTINGS = Settings(qloo_api_key="qloo-secret-xyz", qloo_base_url="https://mock.invalid", qloo_timeout=5, qloo_retries=1,
                        llm_api_key="llm-secret", llm_base_url="https://llm.invalid", llm_model="m", llm_timeout=5)
QLOO_SETTINGS = Settings(qloo_api_key="qloo-secret-xyz", qloo_base_url="https://mock.invalid", qloo_timeout=5, qloo_retries=1,
                         llm_api_key=None, llm_base_url=None, llm_model=None, llm_timeout=5)


def run_async(coro):
    return asyncio.run(coro)


def mock_client(tmp_path, **kw):
    return QlooClient(QLOO_SETTINGS, RunRecorder(tmp_path / "run"), transport=make_transport(), synthetic=True, **kw)


# ---- evidence ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("idx,fit", [(0, 0.5), (1, 1.0), (-1, 0.0), (0.4, 0.7), (5, 1.0), (-5, 0.0)])
def test_index_to_fit(idx, fit):
    assert E.index_to_fit(idx) == pytest.approx(fit)


def test_qloo_fit_from_age_index_means_over_segment_bands(make_intake, store):
    i = make_intake(price=40_000)
    res = score_segments(i, assess(i, store))
    idx = {"24_and_younger": 0.6, "25_to_29": 0.0, "30_to_34": -0.2}
    fit = E.qloo_fit_from_age_index(idx, res.ranked)
    stu = next(s for s in res.ranked if s.id == "students_budget")
    assert fit["students_budget"] == pytest.approx(E.index_to_fit(0.6), abs=1e-3)
    ftu = next(s for s in res.ranked if s.id == "first_time_users")  # 24-, 25-29, 30-34
    assert fit["first_time_users"] == pytest.approx((0.8 + 0.5 + 0.4) / 3, abs=1e-3)
    assert "older_value_seekers" not in fit  # no index for 55+: no data, not zero
    assert stu and ftu


def test_resolve_and_skew_with_mock(make_intake, tmp_path):
    async def go():
        async with mock_client(tmp_path) as c:
            return await E.resolve_and_skew(c, make_intake(competitors=["Tecno", "Infinix"]))
    r = run_async(go())
    assert [a["query"] for a in r["anchors"]] == ["Tecno", "Infinix"] and r["unresolved"] == []
    assert "24_and_younger" in r["age_index"] and set(r["gender_index"]) == {"female", "male"}
    assert any(it["step"] == "demographics" and it["ok"] for it in r["ev"].items)


def test_resolve_and_skew_without_competitors_makes_no_calls(make_intake, tmp_path):
    async def go():
        async with mock_client(tmp_path) as c:
            r = await E.resolve_and_skew(c, make_intake())
            return r, c.calls_used
    r, used = run_async(go())
    assert used == 0 and r["age_index"] == {} and r["anchors"] == []


def test_unresolvable_competitor_is_reported_not_used(make_intake, tmp_path):
    async def go():
        t = make_transport(reject=lambda req: req.url.path == "/search")  # Qloo search fails
        async with QlooClient(QLOO_SETTINGS, RunRecorder(tmp_path / "run"), transport=t, synthetic=True) as c:
            return await E.resolve_and_skew(c, make_intake(competitors=["Tecno"]))
    r = run_async(go())
    assert r["unresolved"] == ["Tecno"] and r["anchors"] == [] and r["age_index"] == {}
    assert r["ev"].items[0]["ok"] is False


def test_gather_segments_builds_per_segment_evidence(make_intake, store, tmp_path):
    i = make_intake(price=40_000, max_personas=2)
    res = score_segments(i, assess(i, store))

    async def go():
        async with mock_client(tmp_path) as c:
            base = await E.resolve_and_skew(c, i)
            await E.gather_segments(c, i, res.ranked, base["ev"], ["brand", "place"], take=4)
            return base["ev"].items, c.calls_used
    items, used = run_async(go())
    assert used == 2 * (2 + 1)  # per segment: 2 kinds + heatmap
    labels = {it["segment"] for it in items}
    assert labels == {s.label for s in res.ranked}
    assert all(it["ok"] for it in items)
    view = E.segment_view(items, res.ranked[0])
    assert set(view["lists"]) == {"brand", "place"} and view["lists"]["brand"]["evidence_id"].startswith("E")
    assert view["areas"]["named_by_nearby_place"], "heatmap areas should be named from nearby returned places"
    assert E.place_names(items, res.ranked[0].label) >= {"Nkoyo Lagos"}
    assert "Zara" in E.entity_names(items, res.ranked[0].label)


def test_segment_view_reports_failures(make_intake, store):
    items = [{"id": "E001", "step": "affinity", "label": "x", "segment": "S", "ok": False, "error": "HTTP 400", "data": None}]
    from discover.engine.personas.scoring import SegmentScore
    seg = SegmentScore("a", "S", "d", ("25_to_29",), None, 0.5, "low", {}, {}, [], [])
    assert E.segment_view(items, seg)["missing"][0]["error"] == "HTTP 400"


# ---- writer --------------------------------------------------------------------------------------------------
@pytest.fixture
def bundle_and_seg(make_intake, store, tmp_path):
    i = make_intake(price=600_000, competitors=["Tecno"], max_personas=2)
    aff = assess(i, store)
    res = score_segments(i, aff)

    async def go():
        async with mock_client(tmp_path) as c:
            base = await E.resolve_and_skew(c, i)
            await E.gather_segments(c, i, res.ranked, base["ev"], ["brand", "place"], take=4)
            return base
    base = run_async(go())
    bundle = {"evidence": base["ev"].items, "anchors": base["anchors"], "unresolved": [], "age_index": base["age_index"],
              "gender_index": base["gender_index"]}
    return i, aff, res, bundle


def test_price_barriers_from_numbers(make_intake, store):
    i = make_intake(price=600_000)
    aff = assess(i, store)
    res = score_segments(i, aff)
    he = next(s for s in res.ranked if s.id == "high_earners_young")
    b = W.price_barriers(he, aff)
    assert b and all(x["basis"] == "calculated" for x in b)
    assert any("out of reach" in x["text"] or "stretch" in x["text"] for x in b)


def test_validate_persona_drops_invented_places_and_tastes(bundle_and_seg):
    i, aff, res, bundle = bundle_and_seg
    seg = res.ranked[0]
    brand_id = next(e["id"] for e in bundle["evidence"] if e.get("segment") == seg.label and e["label"].endswith(":brand"))
    raw = {"segment_id": "WRONG", "name": "Ada", "headline": "h", "who": "w",
           "tastes": [{"name": "Zara", "kind": "brand", "evidence": ["E999"]}, {"name": "Totally Invented Brand", "kind": "brand"}],
           "where_to_reach": [{"place": "Nkoyo Lagos", "why": "popular"}, {"place": "Victoria Island", "why": "rich area"}],
           "motivations": [{"text": "likes brands", "basis": "evidence", "evidence": ["E999"]},
                           {"text": "follows Zara and similar brands", "basis": "evidence", "evidence": [brand_id]}],
           "messages": [{"angle": "a", "text": "t", "basis": "evidence", "evidence": []}],
           "platforms": [{"platform": "TikTok", "why": "young", "basis": "evidence"}] * 5,
           "events": [{"idea": "campus tour", "why": "reach students"}] * 4,
           "objections": [{"text": "pricey", "basis": "calculated"}]}
    p = W.validate_persona(raw, seg, bundle["evidence"], aff)
    assert p["segment_id"] == seg.id
    assert [t["name"] for t in p["tastes"]] == ["Zara"] and p["tastes"][0]["evidence"][0].startswith("E")
    assert [w["place"] for w in p["where_to_reach"]] == ["Nkoyo Lagos"]
    assert p["validation"]["dropped"] == {"tastes": 1, "where_to_reach": 1}
    assert p["motivations"][0]["basis"] == "interpretation" and p["motivations"][1]["basis"] == "evidence"
    assert p["messages"][0]["basis"] == "interpretation"
    assert p["platforms"] == []  # platforms never come from the LLM; without a culture digest there are none
    assert len(p["events"]) == 2 and {x["basis"] for x in p["events"]} == {"interpretation"}
    assert p["validation"]["downgraded_to_interpretation"] == 3  # motivation, message and objection overclaimed
    assert p["objections"][0]["basis"] == "calculated"          # the system-computed barrier leads
    assert [o["basis"] for o in p["objections"] if o["text"] == "pricey"] == ["interpretation"]  # the model's never 'calculated'
    nk = next(w for w in p["where_to_reach"] if w["place"] == "Nkoyo Lagos")
    assert "model_note" not in nk and nk["affinity"] is not None and nk["evidence"]


def test_validate_persona_tolerates_garbage(bundle_and_seg):
    i, aff, res, bundle = bundle_and_seg
    p = W.validate_persona({"tastes": "x", "messages": [1, None, {"text": ""}], "where_to_reach": [5], "platforms": [None]},
                           res.ranked[0], bundle["evidence"], aff)
    assert p["tastes"] == [] and p["messages"] == [] and p["platforms"] == [] and p["where_to_reach"] == []
    json.dumps(p)


def test_template_persona_uses_only_returned_data(bundle_and_seg):
    i, aff, res, bundle = bundle_and_seg
    seg = res.ranked[0]
    view = E.segment_view(bundle["evidence"], seg)
    p = W.template_persona(seg, view, aff)
    assert p["messages"] == [] and p["platforms"] == [] and p["motivations"] == []
    assert all(t["evidence"] for t in p["tastes"]) and all(w["evidence"] for w in p["where_to_reach"])


def fake_llm_transport(good: bool = True, status: int = 200):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body)
        if status != 200:
            return httpx.Response(status, json={"error": "x"})
        payload = json.loads(body["messages"][1]["content"])
        if "segment" not in payload:  # identity check, market map: nothing useful to say
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]})
        seg = payload["segment"]["id"]
        brand = next(iter(payload["qloo"]["lists"].get("brand", {}).get("items", [{}])), {}).get("name", "x")
        persona = {"segment_id": seg, "name": "Tobi, the saver", "headline": "wants value", "who": "student",
                   "tastes": [{"name": brand, "kind": "brand"}, {"name": "Invented Co", "kind": "brand"}],
                   "where_to_reach": [{"place": "Not A Real Place", "why": "x"}],
                   "messages": [{"angle": "value", "text": "Long battery for lectures", "basis": "interpretation", "evidence": []}],
                   "platforms": [{"platform": "WhatsApp", "why": "common among the age group"}]}
        content = json.dumps(persona) if good else "not json at all"
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    return httpx.MockTransport(handler), seen


def test_write_personas_with_llm_validates_and_numbers(bundle_and_seg, tmp_path):
    i, aff, res, bundle = bundle_and_seg
    t, seen = fake_llm_transport()
    llm = LLMClient(LLM_SETTINGS, RunRecorder(tmp_path / "r2"), transport=t)
    ps = run_async(W.write_personas(llm, i, aff, res.ranked, bundle))
    assert [p["rank"] for p in ps] == [1, 2] and {p["source"] for p in ps} == {"llm"}
    assert all(p["tastes"] and p["tastes"][0]["name"] != "Invented Co" for p in ps)
    assert all(p["where_to_reach"] == [] for p in ps)
    assert all(p["validation"]["dropped"]["tastes"] == 1 and p["validation"]["dropped"]["where_to_reach"] == 1 for p in ps)
    assert len(seen) == 2  # one call per persona
    sent = json.loads(seen[0]["messages"][1]["content"])
    assert sent["affordability"]["tier"] == aff.tier and "competitor_audience_skew" in sent
    assert "api_key" not in json.dumps(seen[0]) and "llm-secret" not in json.dumps(seen[0])


def test_write_personas_falls_back_to_template_when_llm_fails(bundle_and_seg, tmp_path):
    i, aff, res, bundle = bundle_and_seg
    t, _ = fake_llm_transport(good=False)
    llm = LLMClient(LLM_SETTINGS, RunRecorder(tmp_path / "r3"), transport=t)
    ps = run_async(W.write_personas(llm, i, aff, res.ranked, bundle))
    assert {p["source"] for p in ps} == {"template"}
    assert all(any("LLM failed" in c for c in p["caveats"]) for p in ps)


def test_llm_client_backs_off_on_429_then_succeeds(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, json={"error": "rate"})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{\"ok\": 1}"}}]})
    llm = LLMClient(LLM_SETTINGS, RunRecorder(tmp_path / "r4"), transport=httpx.MockTransport(handler))
    waited = []

    async def fake_sleep(s):
        waited.append(s)
    llm._sleep = fake_sleep
    assert run_async(llm.chat_json("t", "s", "u")) == {"ok": 1}
    assert waited == [2.0] and len(calls) == 2


def test_markdown_labels_every_basis(bundle_and_seg, tmp_path):
    i, aff, res, bundle = bundle_and_seg
    t, _ = fake_llm_transport()
    llm = LLMClient(LLM_SETTINGS, RunRecorder(tmp_path / "r5"), transport=t)
    ps = run_async(W.write_personas(llm, i, aff, res.ranked, bundle))
    md = W.markdown(i, aff, ps, bundle, ["note"], ["World Bank Open Data (CC BY 4.0)"], synthetic=True)
    assert "SYNTHETIC DATA" in md and "[Qloo]" in md and "[LLM interpretation]" in md and "[calculated]" in md
    assert "Limits of this report" in md and "World Bank" in md and "Qloo Taste AI" in md


# ---- runner / CLI --------------------------------------------------------------------------------------------
def opts(make_intake, tmp_path, **kw):
    base = dict(intake=make_intake(price=40_000, competitors=["Tecno"], max_personas=3), out=tmp_path / "runs", mock=True, zip=True)
    base.update(kw)
    return PersonaOptions(**base)


def test_runner_mock_end_to_end_writes_the_run_folder(make_intake, store, tmp_path):
    code, run, summary = run_async(execute_personas(opts(make_intake, tmp_path), QLOO_SETTINGS, store))
    assert code == 0 and summary["status"] == "complete" and summary["synthetic"] is True
    names = {p.name for p in run.iterdir()}
    assert {"00_input.json", "01_segments_before_qloo.json", "02_segments_after_qloo.json", "03_evidence.json",
            "04_personas.json", "04_personas.md", "99_run_summary.json", "calls.jsonl"} <= names
    res = json.loads((run / "04_personas.json").read_text())
    assert len(res["personas"]) == 3 and res["synthetic"] is True
    assert res["scoring"]["ranked_by"].endswith("Qloo audience fit")
    assert all(it["synthetic"] for it in json.loads((run / "03_evidence.json").read_text()))
    assert "SYNTHETIC" in (run / "04_personas.md").read_text()
    z = Path(summary["zip"])
    assert any(n.endswith("04_personas.md") for n in zipfile.ZipFile(z).namelist())


def test_runner_reranks_with_qloo_and_fetches_evidence_only_for_final_segments(make_intake, store, tmp_path):
    code, run, summary = run_async(execute_personas(opts(make_intake, tmp_path), QLOO_SETTINGS, store))
    after = json.loads((run / "02_segments_after_qloo.json").read_text())
    final_labels = {s["label"] for s in after["ranked"]}
    ev = json.loads((run / "03_evidence.json").read_text())
    assert {e["segment"] for e in ev if e["segment"]} == final_labels
    assert all("qloo_fit" in s["components"] for s in after["ranked"] if s["id"] in {"students_budget", "first_time_users"})


def test_runner_with_llm_and_fake_provider(make_intake, store, tmp_path):
    t, seen = fake_llm_transport()
    code, run, summary = run_async(execute_personas(opts(make_intake, tmp_path), LLM_SETTINGS, store, llm_transport=t))
    assert summary["persona_sources"] == ["llm"] * 3 and summary["llm_calls"] == 5 and code == 0  # 3 personas + identity check + market map
    assert len(seen) == 5
    res = json.loads((run / "04_personas.json").read_text())
    assert all(x["basis"] == "calculated" for p in res["personas"] for x in p["platforms"])  # computed in code, never by the LLM
    plats = {x["platform"] for p in res["personas"] for x in p["platforms"]}
    assert "Instagram" in plats and "WhatsApp" not in plats and "Wikidata" not in plats  # allowlist from data; the LLM's guess is ignored
    def _payload(b):
        try:
            return json.loads(b["messages"][1]["content"])
        except ValueError:
            return {}
    persona_calls = [c for c in map(_payload, seen) if "segment" in c]
    assert persona_calls and all("culture" in c["qloo"] and "platforms" not in c["qloo"]["culture"] for c in persona_calls)
    assert any(c["qloo"]["culture"]["sentences"] for c in persona_calls)
    assert len(list((run / "llm").glob("*_persona_*.json"))) == 3


def test_runner_llm_failure_gives_partial_exit_code(make_intake, store, tmp_path):
    t, _ = fake_llm_transport(status=500)
    code, run, summary = run_async(execute_personas(opts(make_intake, tmp_path), LLM_SETTINGS, store, llm_transport=t))
    assert code == 1 and summary["llm_failed_personas"] == 3 and summary["persona_sources"] == ["template"] * 3


def test_runner_never_writes_secrets(make_intake, store, tmp_path):
    t, _ = fake_llm_transport()
    _, run, _ = run_async(execute_personas(opts(make_intake, tmp_path), LLM_SETTINGS, store, llm_transport=t))
    blob = "".join(p.read_text(errors="ignore") for p in run.rglob("*") if p.is_file())
    assert "qloo-secret-xyz" not in blob and "llm-secret" not in blob


def test_runner_rejects_invalid_intake(make_intake, store, tmp_path):
    code, run, summary = run_async(execute_personas(opts(make_intake, tmp_path, intake=make_intake(price=-1)), QLOO_SETTINGS, store))
    assert code == 3 and summary["status"] == "invalid_intake" and summary["errors"]


def test_runner_reports_missing_reference_data(make_intake, tmp_path):
    from discover.engine.personas.refdata.store import ReferenceStore
    empty = ReferenceStore(cache_path=None, snapshot_path=None)
    code, run, summary = run_async(execute_personas(opts(make_intake, tmp_path), QLOO_SETTINGS, empty))
    assert code == 3 and summary["status"] == "missing_reference_data"


def test_runner_requires_a_qloo_key_unless_mock_or_dry_run(make_intake, store, tmp_path):
    nokey = Settings(qloo_api_key=None, qloo_base_url="https://x.invalid", qloo_timeout=5, qloo_retries=1,
                     llm_api_key=None, llm_base_url=None, llm_model=None, llm_timeout=5)
    code, _, summary = run_async(execute_personas(opts(make_intake, tmp_path, mock=False), nokey, store))
    assert code == 3 and summary["status"] == "no_qloo_key"


def test_runner_dry_run_makes_no_calls_and_writes_plan(make_intake, store, tmp_path):
    code, run, summary = run_async(execute_personas(opts(make_intake, tmp_path, mock=False, dry_run=True), QLOO_SETTINGS, store))
    assert code == 0 and summary["status"] == "dry_run"
    assert (run / "04_personas.md").exists() and summary["http_requests"] == 0


def test_runner_no_competitors_still_produces_personas(make_intake, store, tmp_path):
    o = opts(make_intake, tmp_path, discover=False)
    o.intake = make_intake(price=40_000, max_personas=2)
    code, run, summary = run_async(execute_personas(o, QLOO_SETTINGS, store))
    res = json.loads((run / "04_personas.json").read_text())
    assert code == 0 and len(res["personas"]) == 2 and res["anchor_audience"]["age_index"] == {}
    assert not res["scoring"]["ranked_by"].endswith("Qloo audience fit")


def test_cli_personas_mock(tmp_path, capsys):
    argv = ["personas", "--name", "Budget phone", "--description", "Affordable phone with long battery life for students",
            "--category", "smartphone", "--price", "40000", "--currency", "NGN", "--location", "Lagos",
            "--competitor", "Tecno", "--mock", "--max-personas", "2", "--cache", str(tmp_path / "c.json"),
            "--out", str(tmp_path / "runs")]
    code = main(argv)
    out = capsys.readouterr().out
    assert code == 0 and "complete" in out and "send me" in out


def test_cli_personas_invalid_intake(tmp_path, capsys):
    assert main(["personas", "--name", "x", "--mock", "--cache", str(tmp_path / "c.json"), "--out", str(tmp_path)]) == 3
    assert "intake problems" in capsys.readouterr().out


# ---- anchor matching, shared-evidence notes (from the first real run) -----------------------------------------
@pytest.mark.parametrize("query,names,expected,how", [
    ("Tecno", ["TECNO Mobile", "BandLab"], "TECNO Mobile", "prefix"),
    ("Infinix", ["Infinix Mobile"], "Infinix Mobile", "prefix"),
    ("Nike", ["Nike", "Nike Factory Store"], "Nike", "exact"),
    ("Anime", ["Anime Studio X", "Something"], None, None),          # fuzzy first hit must never be accepted
    ("Tecno", ["BandLab", "SpaceX", "MIT"], None, None),
    ("Tecno", ["Technology Park"], None, None),                     # prefix of a word is not a word prefix
    ("Dano", ["Dano Nigeria"], "Dano Nigeria", "prefix"),
    ("Apple", ["Apple Records Group Of Companies Ltd Weird"], None, None),
])
def test_pick_anchor(query, names, expected, how):
    cands = [{"entity_id": f"id{i}", "name": n} for i, n in enumerate(names)]
    top, h = E.pick_anchor(cands, query)
    assert (top["name"] if top else None) == expected and h == how


def test_pick_anchor_needs_an_id():
    assert E.pick_anchor([{"name": "TECNO Mobile"}], "Tecno") == (None, None)


def _ev(segment, kind, names, eid, aff=0.7):
    return {"id": eid, "step": "affinity", "label": f"{segment}:{kind}", "segment": segment, "ok": True,
            "data": {"kind": kind, "entities": [{"name": n, "affinity": aff} for n in names]}}


def test_shared_evidence_notes_flag_identical_ages_and_overlapping_places():
    from discover.engine.personas.scoring import SegmentScore
    a = SegmentScore("a", "Students", "d", ("24_and_younger",), None, 0.5, "low", {}, {}, [], [])
    b = SegmentScore("b", "First timers", "d", ("24_and_younger",), None, 0.5, "low", {}, {}, [], [])
    c = SegmentScore("c", "Households", "d", ("35_to_44",), None, 0.5, "low", {}, {}, [], [])
    items = [_ev("Students", "place", ["UoL", "Hotel", "Beach"], "E1"), _ev("First timers", "place", ["UoL", "Hotel", "Beach"], "E2"),
             _ev("Households", "place", ["UoL", "Hotel", "Beach", "Mall"], "E3")]
    notes = E.shared_evidence_notes(items, [a, b, c], "Lagos")
    assert any("Students and First timers" in n and "identical lists" in n for n in notes)
    assert any("overlap by" in n and "Lagos" in n for n in notes)


def test_shared_evidence_notes_quiet_when_lists_differ():
    from discover.engine.personas.scoring import SegmentScore
    a = SegmentScore("a", "A", "d", ("24_and_younger",), None, 0.5, "low", {}, {}, [], [])
    b = SegmentScore("b", "B", "d", ("35_to_44",), None, 0.5, "low", {}, {}, [], [])
    items = [_ev("A", "place", ["P1", "P2"], "E1"), _ev("B", "place", ["P3", "P4"], "E2")]
    assert E.shared_evidence_notes(items, [a, b], "Lagos") == []


def test_place_affinity_lookup():
    items = [_ev("S", "place", ["A", "B"], "E1", aff=0.61)]
    assert E.place_affinity(items, "S") == {"A": 0.61, "B": 0.61} and E.place_affinity(items, "Other") == {}


def test_markdown_shows_prefix_match_and_place_affinity(bundle_and_seg, tmp_path):
    i, aff, res, bundle = bundle_and_seg
    bundle["anchors"] = [{"query": "Tecno", "entity_id": "x", "name": "TECNO Mobile", "matched_by": "prefix"}]
    t, _ = fake_llm_transport()
    llm = LLMClient(LLM_SETTINGS, RunRecorder(tmp_path / "r6"), transport=t)
    ps = run_async(W.write_personas(llm, i, aff, res.ranked, bundle))
    ps[0]["where_to_reach"] = [{"place": "Nkoyo Lagos", "affinity": 0.7, "evidence": ["E006"], "basis": "evidence"}]
    md = W.markdown(i, aff, ps, bundle, [], ["World Bank"], False)
    assert "matched to Qloo's 'TECNO Mobile'" in md
    assert "affinity 0.7" in md and "model's note" not in md and "Score parts:" in md and "Strongest skew" in md
    assert "inspired by" in md or all(not p["messages"] or not p["messages"][0]["evidence"] for p in ps)


def test_runner_writes_evidence_notes(make_intake, store, tmp_path):
    o = opts(make_intake, tmp_path)
    code, run, summary = run_async(execute_personas(o, QLOO_SETTINGS, store))
    res = json.loads((run / "04_personas.json").read_text())
    assert "evidence_notes" in res and any("overlap by" in n or "identical lists" in n for n in res["evidence_notes"])


# ---- claim screening (invented specs, social proof, untraceable citations) -------------------------------------
@pytest.mark.parametrize("text,drop,verify", [
    ("40 hrs on a single charge", True, []),
    ("Only 40,000 NGN for a phone that lasts all day", False, []),
    ("Our battery outlasts the competition", True, []),
    ("Chosen by fans of ALAT By Wema", True, []),
    ("Trusted by thousands", True, []),
    ("Smooth gaming on a budget", False, ["gaming"]),
    ("Long battery for lectures", False, []),
    ("Takes 12MP photos", True, []),
    ("A 5g camera phone", False, ["camera", "5g"]),
])
def test_screen_claim(make_intake, text, drop, verify):
    i = make_intake(price=40_000, description="Affordable phone with long battery life for students")
    d, v = W.screen_claim(text, i)
    assert d is drop and v == verify


def test_numbers_in_product_text_are_allowed(make_intake):
    i = make_intake(price=40_000, description="A phone with 64GB storage", features=["dual sim", "2 year warranty"])
    assert W.screen_claim("64GB of room", i)[0] is False
    assert W.screen_claim("2 year cover", i)[0] is False
    assert W.screen_claim("128GB of room", i)[0] is True


def test_validate_drops_invented_specs_and_flags_unsupported_features(bundle_and_seg):
    i, aff, res, bundle = bundle_and_seg
    i.price = 600_000
    seg = res.ranked[0]
    raw = {"messages": [{"angle": "a", "text": "40 hours of battery", "evidence": []},
                        {"angle": "b", "text": "Best gaming experience", "evidence": []},
                        {"angle": "c", "text": "Great camera for the price", "evidence": []},
                        {"angle": "d", "text": "Long battery life in your pocket", "evidence": []}],
           "motivations": [{"text": "Wants to be seen with top-rated brands", "evidence": []}]}
    p = W.validate_persona(raw, seg, bundle["evidence"], aff, i)
    texts = [m["text"] for m in p["messages"]]
    assert "40 hours of battery" not in texts and "Long battery life in your pocket" in texts
    cam = next(m for m in p["messages"] if "camera" in m["text"])
    assert cam["verify_product_supports"] == ["camera"]
    assert p["validation"]["dropped"]["messages"] == 1 and p["validation"]["dropped"]["motivations"] == 1


def test_citations_must_be_traceable_to_the_text(bundle_and_seg):
    i, aff, res, bundle = bundle_and_seg
    seg = res.ranked[0]
    brand_id = next(e["id"] for e in bundle["evidence"] if e.get("segment") == seg.label and e["label"].endswith(":brand"))
    raw = {"motivations": [{"text": "Cares about low price", "basis": "evidence", "evidence": [brand_id]},
                           {"text": "Follows Zara", "basis": "evidence", "evidence": [brand_id]}],
           "messages": [{"angle": "x", "text": "A phone that fits your budget", "evidence": [brand_id]},
                        {"angle": "y", "text": "For people who like Zara", "evidence": [brand_id]}]}
    p = W.validate_persona(raw, seg, bundle["evidence"], aff, i)
    m = {x["text"]: x for x in p["motivations"]}
    assert m["Cares about low price"]["basis"] == "interpretation" and m["Cares about low price"]["evidence"] == []
    assert m["Follows Zara"]["basis"] == "evidence" and m["Follows Zara"]["evidence"] == [brand_id]
    g = {x["text"]: x for x in p["messages"]}
    assert g["A phone that fits your budget"]["evidence"] == [] and g["For people who like Zara"]["evidence"] == [brand_id]


def test_skew_summary():
    s = W.skew_summary({"24_and_younger": -0.04, "25_to_29": 0.59, "30_to_34": 0.75, "35_to_44": -0.86}, {"male": 0.68, "female": -0.68})
    assert "30_to_34 (+0.75)" in s and "25_to_29 (+0.59)" in s and "35_to_44 (-0.86)" in s and "male (+0.68)" in s
    assert W.skew_summary({}, {}) == ""
    assert "No strong gender lean" in W.skew_summary({"a": 0.1}, {"male": 0.05})


def test_fake_llm_cannot_smuggle_invented_numbers_through_write_personas(bundle_and_seg, tmp_path):
    i, aff, res, bundle = bundle_and_seg

    def handler(req):
        persona = {"messages": [{"angle": "x", "text": "40 hrs on one charge", "evidence": []}], "tastes": [], "platforms": []}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(persona)}}]})
    llm = LLMClient(LLM_SETTINGS, RunRecorder(tmp_path / "r7"), transport=httpx.MockTransport(handler))
    ps = run_async(W.write_personas(llm, i, aff, res.ranked, bundle))
    assert all(p["messages"] == [] and p["validation"]["dropped"]["messages"] == 1 for p in ps)
