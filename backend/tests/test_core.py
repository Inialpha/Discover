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
    b = apply_overrides(heuristic_brief("x"), gender="men", age="30-40", location="Abuja")
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
                      location="Lagos", mock=True, zip=False)
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
