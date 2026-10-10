import asyncio, json
from pathlib import Path
import httpx
from discover.qloo import calls, normalize as nz
from discover.qloo.client import QlooClient
from discover.qloo.demographics import age_range_to_buckets
from discover.qloo.geo import decode, encode
from discover.qloo.mock import make_transport
from discover.recorder import RunRecorder
from discover.runner import RunOptions, execute
from discover.modes.business.brief import heuristic_brief, apply_overrides


def test_age_buckets():
    assert age_range_to_buckets(25, 35) == ["25_to_29", "30_to_34"]
    assert age_range_to_buckets(18, 24) == ["24_and_younger"]


def test_geohash_roundtrip():
    lat, lon = decode(encode(6.5244, 3.3792, 6))
    assert abs(lat - 6.5244) < 0.02 and abs(lon - 3.3792) < 0.02


def test_heuristic_brief():
    b = heuristic_brief("what does women from 25 to 35 in Lagos like, what media?")
    assert b.location == "Lagos" and b.segments[0].gender == "female"
    assert b.segments[0].age_buckets == ["25_to_29", "30_to_34"] and b.domains == ["movie", "tv_show", "artist", "podcast"]


def test_overrides_win():
    b = apply_overrides(heuristic_brief("x"), gender="men", age="30-40", locations=["Abuja"])
    assert b.location == "Abuja" and b.segments[0].gender == "male"


def test_normalize_real_samples(examples):
    files = list(examples.rglob("*.json"))
    assert files
    seen = 0
    for f in files:
        data = json.loads(f.read_text())
        body = data.get("response", data) if isinstance(data, dict) else data
        if not isinstance(body, dict):
            continue
        for fn in (nz.entities_from_insights, nz.entities_from_search):
            for e in fn(body):
                assert e["name"]; seen += 1
    assert seen > 0


def _run(coro):
    return asyncio.run(coro)


def test_variant_fallback_and_redaction(settings, tmp_path):
    rec = RunRecorder(tmp_path)
    t = make_transport(lambda r: "types" in r.url.params)  # reject first spelling
    async def go():
        async with QlooClient(settings, rec, transport=t) as c:
            return await c.call(calls.search_entities("x", "Nike", "brand"))
    r = _run(go())
    assert r.ok and r.variant_index == 1 and len(r.files) == 2
    for f in tmp_path.rglob("*.json"):
        assert "secret-test-key" not in f.read_text()


def test_auth_failure_stops(settings, tmp_path):
    t = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "no"}))
    async def go():
        async with QlooClient(settings, RunRecorder(tmp_path), transport=t) as c:
            a = await c.call(calls.search_entities("a", "x", "brand"))
            b = await c.call(calls.search_entities("b", "y", "brand"))
            return a, b, c
    a, b, c = _run(go())
    assert not a.ok and c.auth_failed and b.skipped_reason


def test_retry_on_429(settings, tmp_path, monkeypatch):
    n = {"i": 0}
    def h(r):
        n["i"] += 1
        return httpx.Response(429, headers={"retry-after": "0"}) if n["i"] == 1 else httpx.Response(200, json={"results": []})
    async def go():
        async with QlooClient(settings, RunRecorder(tmp_path), transport=httpx.MockTransport(h)) as c:
            return await c.call(calls.search_entities("a", "x", None))
    assert _run(go()).ok and n["i"] == 2


def test_dry_run_makes_no_requests(settings, tmp_path):
    t = httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError("network used")))
    async def go():
        async with QlooClient(settings, RunRecorder(tmp_path), transport=t, dry_run=True) as c:
            return await c.call(calls.search_entities("a", "x", "brand"))
    r = _run(go())
    assert r.dry_run and (tmp_path / r.file).exists()


def test_mock_e2e(settings, tmp_path):
    opts = RunOptions(question="advise ad for my sneaker brand in Lagos", out=tmp_path, own_brand="Nike",
                      competitors=["Adidas"], keywords=["streetwear"], gender="women", age="25-35",
                      locations=["Lagos"], mock=True, zip=False)
    code, run_dir, s = _run(execute(opts, settings))
    assert code == 0 and s["qloo_ok"] == s["qloo_calls"] > 5
    for name in ("01_brief.json", "03_evidence.json", "04_report.md", "99_run_summary.json", "calls.jsonl"):
        assert (run_dir / name).exists()
    ev = json.loads((run_dir / "03_evidence.json").read_text())
    assert all(e["synthetic"] for e in ev) and {"resolve", "taste", "affinity", "demographics", "heatmap"} <= {e["step"] for e in ev}


def test_no_key_exit3(settings, tmp_path):
    from dataclasses import replace
    code, _, s = _run(execute(RunOptions(question="q", out=tmp_path), replace(settings, qloo_api_key=None)))
    assert code == 3


def test_pick_tag_rejects_junk():
    from discover.modes.business.pipeline import pick_tag
    cands = [
        {"id": "urn:tag:specialty_dish:place:35_25", "name": "35 25"},
        {"id": "urn:tag:specialty_dish:place:sneakers", "name": "Sneakers"},
        {"id": "urn:tag:genre:brand:fashion:footwear:sneakers", "name": "Sneakers"},
    ]
    assert pick_tag(cands, "25-35", "advertising") is None
    assert pick_tag(cands, "sneakers", "advertising")["id"].startswith("urn:tag:genre:brand")


def test_keywords_drop_demographics():
    from discover.modes.business.brief import Brief, clean_keywords
    b = Brief(question="q", locations=["Lagos"], keywords=["women", "25-35", "Lagos", "streetwear", "Streetwear"])
    assert clean_keywords(b).keywords == ["streetwear"]


def test_compare_and_heatmap_real_shapes():
    cmp = {"results": {"tags": [{"tag_id": "t1", "name": "Fashion", "subtype": "s", "query": {"score": 0.73}}]}}
    assert nz.compare_from_body(cmp)["tags"][0]["score"] == 0.73
    hm = {"results": {"heatmap": [{"location": {"latitude": 6.6, "longitude": 3.4, "geohash": "s14mzk"},
                                   "query": {"affinity": 1, "demographics_affinity": 0.9, "affinity_rank": 0.6}}]}}
    p = nz.heatmap_from_body(hm)[0]
    assert p["geohash"] == "s14mzk" and p["demographics_affinity"] == 0.9


def test_evidence_fits_budget():
    from discover.modes.business.synthesis import fit_evidence
    ents = [{"name": f"E{i}", "affinity": 0.9, "tags": [{"name": f"t{j}"} for j in range(8)], "disambiguation": "x" * 100} for i in range(10)]
    items = [{"id": f"E{i}", "step": "affinity", "label": "l", "ok": True, "data": {"kind": "movie", "entities": ents}} for i in range(12)]
    _, text = fit_evidence(items, 3000)
    assert len(text) <= 3000


def test_heatmap_named_by_nearest_place():
    from discover.modes.business.pipeline import Evidence, _annotate_heatmaps
    ev = Evidence()
    ev.items = [
        {"id": "E001", "step": "affinity", "ok": True, "segment": "S", "data": {"kind": "place", "entities": [
            {"name": "Near Cafe", "location": {"lat": 6.45, "lon": 3.40}}, {"name": "Far Cafe", "location": {"lat": 7.5, "lon": 4.5}}]}},
        {"id": "E002", "step": "heatmap", "ok": True, "segment": "S", "data": {"points": [
            {"lat": 6.451, "lon": 3.401}, {"lat": 9.0, "lon": 8.0}]}},
    ]
    _annotate_heatmaps(ev)
    pts = ev.items[1]["data"]["points"]
    assert pts[0]["nearby_places"][0]["name"] == "Near Cafe" and pts[1]["nearby_places"] == []


def test_confidence_capped_and_basis_set():
    from discover.modes.business.synthesis import validate_report
    items = [{"id": "E001"}]
    r = validate_report({"findings": [{"claim": "c", "evidence_ids": ["E001"], "confidence": "high"}],
                         "media_recommendations": [{"channel_or_title": "Instagram", "evidence_ids": []}]}, items)
    assert r["findings"][0]["confidence"] == "medium" and r["media_recommendations"][0]["basis"] == "interpretation"


def test_llm_truncation_retries(settings, tmp_path):
    import json as _j
    from dataclasses import replace
    from discover.llm.client import LLMClient
    calls = []
    def h(req):
        body = _j.loads(req.content); calls.append(body["max_tokens"])
        fin = "length" if len(calls) == 1 else "stop"
        return httpx.Response(200, json={"choices": [{"finish_reason": fin, "message": {"content": '{"a": 1}'}}]})
    s = replace(settings, llm_api_key="k", llm_base_url="https://llm.invalid/v1", llm_model="m")
    out = _run(LLMClient(s, RunRecorder(tmp_path), transport=httpx.MockTransport(h)).chat_json("t", "s", "u", max_tokens=1000))
    assert out == {"a": 1} and calls == [1000, 1500]


def test_multi_location_pipeline_and_coverage(settings, tmp_path):
    opts = RunOptions(question="content for women 25-35", out=tmp_path, gender="women", age="25-35",
                      locations=["New York", "Mumbai"], mock=True, zip=False)
    code, run_dir, s = _run(execute(opts, settings))
    ev = json.loads((run_dir / "03_evidence.json").read_text())
    segs = {e.get("segment") for e in ev if e.get("segment")}
    assert any("New York" in x for x in segs) and any("Mumbai" in x for x in segs)
    rep = json.loads((run_dir / "04_report.json").read_text())["report"]
    assert set(rep["data_coverage"]["per_location"]) >= {"New York", "Mumbai"}
    assert "Data coverage" in (run_dir / "04_report.md").read_text()


def test_coverage_probe_mock(settings, tmp_path):
    from discover.runner import execute_coverage
    code, run_dir, s = _run(execute_coverage(["Lagos", "New York"], "women", "25-35", ["movie", "artist", "place"], 5,
                                             tmp_path, settings, mock=True, zip_=False))
    res = json.loads((run_dir / "coverage.json").read_text())
    assert code == 0 and res["synthetic"] and res["locations"]["Lagos"]["country_inferred"] == "mockland"
    assert res["locations"]["New York"]["kinds"]["movie"]["local_share"] == 1.0 and (run_dir / "coverage.md").exists()


def test_goal_content_heuristic():
    assert heuristic_brief("what social media content should I create for women 25-35 in Tokyo").goal == "content"


def test_infer_country_and_local_share():
    from discover.modes.business.coverage import infer_country, local_share
    jp = [{"properties": {"address": "1-1 Maihama, Urayasu, Chiba 279-0031 Japan"}}, {"properties": {"address": "Minato City, Tokyo 106-6150 Japan"}}]
    us = [{"properties": {"address": "20 W 34th St. New York, NY 10001"}}]
    uk = [{"properties": {"address": "Bankside London SE1 9TG United Kingdom"}}]
    assert infer_country(jp) == "japan" and infer_country(us) == "united states" and infer_country(uk) == "united kingdom"
    movies = [{"properties": {"release_country": ["Japan"]}}, {"properties": {"release_country": ["United States"]}}, {"properties": {}}]
    assert local_share("movie", movies, "japan") == 0.5 and local_share("artist", movies, "japan") is None


def test_entity_pick_requires_name_match_and_interests_dedupe():
    from discover.modes.business.pipeline import _pick
    from discover.modes.business.brief import Brief, clean_keywords
    cands = [{"entity_id": "1", "name": "Rin: Daughters of Mnemosyne"}, {"entity_id": "2", "name": "Attack on Titan"}]
    assert _pick(cands, "Anime") is None
    assert _pick([{"entity_id": "9", "name": "King of Boys"}], "king of boys")["entity_id"] == "9"
    b = Brief(question="q", interests=[{"name": "King of Boys", "kind": "movie"}, {"name": "king of boys", "kind": "movie"}],
              keywords=["King of Boys", "streetwear"])
    clean_keywords(b)
    assert len(b.interests) == 1 and b.keywords == ["streetwear"]
