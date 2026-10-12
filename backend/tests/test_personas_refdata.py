import json
import httpx
import pytest
from discover.personas.refdata import fx as fxmod
from discover.personas.refdata.fx import FxClient, FxError, convert, parse_rates
from discover.personas.refdata.records import FX_PER_USD, GNI_PC_LCU, RefRecord
from discover.personas.refdata.store import SNAPSHOT_PATH, ReferenceStore, age_days
from discover.personas.refdata.worldbank import WorldBankClient, WorldBankError, parse_records

WB_BODY = [{"page": 1, "pages": 1, "per_page": 1000, "total": 3}, [
    {"indicator": {"id": "X", "value": "x"}, "country": {"id": "NG", "value": "Nigeria"}, "countryiso3code": "NGA", "date": "2025", "value": 10.5},
    {"indicator": {"id": "X", "value": "x"}, "country": {"id": "NG", "value": "Nigeria"}, "countryiso3code": "NGA", "date": "2024", "value": None},
    {"indicator": {"id": "X", "value": "x"}, "country": {"id": "JP", "value": "Japan"}, "countryiso3code": "JPN", "date": "2023", "value": 7},
]]
FX_BODY = {"result": "success", "base_code": "USD", "time_last_update_utc": "Sun, 11 Oct 2026 00:02:31 +0000",
           "rates": {"USD": 1, "NGN": 1330.99, "JPY": 158.28, "BAD": "x", "NEG": -1}}


def test_parse_records_drops_nulls_and_keeps_shape():
    r = parse_records(WB_BODY, "X")
    assert [(x.country, x.year, x.value) for x in r] == [("NGA", 2025, 10.5), ("JPN", 2023, 7.0)]
    assert all(x.source == "worldbank" for x in r)


def test_parse_records_empty_and_error():
    assert parse_records([{}, None], "X") == []
    with pytest.raises(WorldBankError):
        parse_records([{"message": [{"id": "120", "value": "Invalid value"}]}], "X")
    with pytest.raises(WorldBankError):
        parse_records({"not": "a list"}, "X")


def _wb(handler, **kw):
    return WorldBankClient(transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def test_wb_client_builds_expected_url_and_params():
    seen = {}

    def h(req):
        seen["url"], seen["q"] = req.url.path, dict(req.url.params)
        return httpx.Response(200, json=WB_BODY)
    with _wb(h) as c:
        out = c.fetch(["NGA", "JPN"], "NY.GNP.PCAP.CN", recent=3)
    assert seen["url"] == "/v2/country/NGA;JPN/indicator/NY.GNP.PCAP.CN"
    assert seen["q"]["format"] == "json" and seen["q"]["mrv"] == "3" and len(out) == 2


def test_wb_client_retries_server_errors_then_succeeds():
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(500) if len(calls) < 3 else httpx.Response(200, json=WB_BODY)
    with _wb(h) as c:
        assert len(c.fetch(["NGA"], "X")) == 2
    assert len(calls) == 3


def test_wb_client_gives_up_and_does_not_retry_client_errors():
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(400, text="bad")
    with _wb(h) as c, pytest.raises(WorldBankError):
        c.fetch(["NGA"], "X")
    assert len(calls) == 1
    calls.clear()

    def h500(req):
        calls.append(1)
        return httpx.Response(503)
    with _wb(h500, retries=2) as c, pytest.raises(WorldBankError):
        c.fetch(["NGA"], "X")
    assert len(calls) == 3


def test_fx_parse_filters_and_stamps():
    recs = parse_rates(FX_BODY)
    codes = {r.country for r in recs}
    assert codes == {"USD", "NGN", "JPY"}  # bad / negative rates dropped
    assert all(r.indicator == FX_PER_USD and r.as_of for r in recs)
    assert {r.country for r in parse_rates(FX_BODY, ["ngn"])} == {"NGN"}


@pytest.mark.parametrize("body", [{"result": "error"}, [], {"result": "success", "base_code": "EUR", "rates": {}},
                                  {"result": "success", "base_code": "USD"}])
def test_fx_parse_rejects_bad_bodies(body):
    with pytest.raises(FxError):
        parse_rates(body)


def test_convert_via_usd():
    rates = {"USD": 1.0, "NGN": 1500.0, "JPY": 150.0}
    assert convert(10, "USD", "NGN", rates) == 15000
    assert convert(1500, "ngn", "usd", rates) == pytest.approx(1)
    assert convert(150, "JPY", "NGN", rates) == pytest.approx(1500)
    assert convert(5, "NGN", "NGN", {}) == 5
    with pytest.raises(KeyError):
        convert(1, "USD", "XXX", rates)


def test_fx_client_end_to_end_with_mock():
    with FxClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=FX_BODY)), sleep=lambda s: None) as c:
        assert len(c.fetch(["NGN"])) == 1


def test_fx_client_failure_raises_fxerror():
    with FxClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)), sleep=lambda s: None) as c, pytest.raises(FxError):
        c.fetch()


def test_snapshot_ships_with_verified_values():
    s = ReferenceStore(cache_path=None)
    assert SNAPSHOT_PATH.exists()
    assert s.latest("NGA", GNI_PC_LCU).value == pytest.approx(1800770.86)
    assert s.latest("NGA", GNI_PC_LCU).year == 2025
    assert s.fx_rates()["NGN"].source == "snapshot"


def test_latest_picks_highest_year_and_cache_overrides_snapshot(tmp_path):
    s = ReferenceStore(cache_path=tmp_path / "c.json", snapshot_path=None)
    s._snapshot = [RefRecord("NGA", "I", 2023, 1, "snapshot", "t"), RefRecord("NGA", "I", 2024, 2, "snapshot", "t")]
    assert s.latest("NGA", "I").value == 2
    s.put_many([RefRecord("NGA", "I", 2024, 99, "worldbank", "t2")])
    assert s.latest("NGA", "I").value == 99 and s.latest("NGA", "I").source == "worldbank"
    assert [r.year for r in s.series("NGA", "I")] == [2024, 2023]
    assert s.latest("NGA", "missing") is None


def test_fx_latest_prefers_newest_fetch():
    s = ReferenceStore(cache_path=None, snapshot_path=None)
    s.put_many([RefRecord("NGN", FX_PER_USD, None, 1, "a", "2026-01-01T00:00:00+00:00")])
    s._cache.append(RefRecord("NGN", FX_PER_USD, None, 2, "b", "2026-02-01T00:00:00+00:00", as_of="x"))
    assert s.fx_rates()["NGN"].value == 2 and s.per_usd()["NGN"] == 2


def test_save_and_reload_roundtrip(tmp_path):
    p = tmp_path / "sub" / "c.json"
    s = ReferenceStore(cache_path=p, snapshot_path=None)
    s.put_many([RefRecord("NGA", "I", 2024, 5.5, "worldbank", "t")])
    s.save()
    again = ReferenceStore(cache_path=p, snapshot_path=None)
    assert again.latest("NGA", "I").value == 5.5
    assert json.loads(p.read_text())["records"][0]["source"] == "worldbank"


def test_corrupt_cache_is_ignored(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json")
    assert ReferenceStore(cache_path=p, snapshot_path=None).latest("A", "B") is None


def test_refresh_writes_cache_and_reports_empty(tmp_path):
    def wb_h(req):
        return httpx.Response(200, json=WB_BODY)
    wb = _wb(wb_h)
    fx = FxClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=FX_BODY)), sleep=lambda s: None)
    s = ReferenceStore(cache_path=tmp_path / "c.json", snapshot_path=None)
    rep = s.refresh(["NGA", "JPN", "KEN"], ["NGN", "JPY"], wb=wb, fx=fx, indicators=["X"])
    assert rep["failed"] == [] and rep["fetched"] == 2 + 3
    assert {"indicator": "X", "country": "KEN"} in rep["empty"]
    assert (tmp_path / "c.json").exists()
    assert s.latest("NGA", "X").value == 10.5 and s.fx_rates()["NGN"].value == 1330.99


def test_refresh_never_raises_and_lists_failures(tmp_path):
    wb = _wb(lambda r: httpx.Response(500), retries=0)
    fx = FxClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)), sleep=lambda s: None, retries=0)
    s = ReferenceStore(cache_path=tmp_path / "c.json", snapshot_path=None)
    rep = s.refresh(["NGA"], ["NGN"], wb=wb, fx=fx, indicators=["X", "Y"])
    assert rep["fetched"] == 0 and len(rep["failed"]) == 3


def test_age_days():
    assert age_days("not a date") is None
    assert age_days("2020-01-01T00:00:00+00:00") > 1000
    assert age_days("2020-01-01T00:00:00") > 1000  # naive treated as UTC


def test_cite_has_provenance():
    c = RefRecord("NGA", "I", 2024, 1.5, "worldbank", "t", as_of="y").cite()
    assert c["source"] == "worldbank" and c["as_of"] == "y" and c["year"] == 2024
