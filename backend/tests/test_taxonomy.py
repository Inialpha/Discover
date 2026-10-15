import json
from pathlib import Path

import httpx
import pytest

from discover import taxonomy as T
from discover.cli import main
from discover.qloo import calls, normalize as nz
from discover.qloo.client import QlooClient
from discover.qloo.mock import make_transport
from discover.recorder import RunRecorder
from tests.test_personas_step2 import QLOO_SETTINGS, run_async


def client(tmp_path, transport=None):
    return QlooClient(QLOO_SETTINGS, RunRecorder(tmp_path / "r"), transport=transport or make_transport(), synthetic=True, concurrency=1)


def test_call_specs_use_documented_parameters():
    s = calls.tag_types("t", "brand")
    assert s.path == "/v2/tags/types" and s.variants[0].params["filter.parents.types"] == "urn:entity:brand"
    s = calls.tags_of_type("x", "urn:tag:genre:brand", query="skincare", page=2)
    assert s.variants[0].params == {"filter.tag.types": "urn:tag:genre:brand", "take": "50", "filter.query": "skincare", "page": "2"}
    ins = calls.insights_entities("p", "l", "brand", calls.Signals(filter_tags=["urn:tag:genre:brand:x"], location="Lagos"))
    assert ins.variants[0].params["filter.tags"] == "urn:tag:genre:brand:x" and "signal.interests.tags" not in ins.variants[0].params


def test_tag_types_parse():
    body = {"results": {"tag_types": [{"id": "urn:tag:genre:brand", "name": "Genre"}]}}
    assert nz.tag_types_from_body(body) == [{"id": "urn:tag:genre:brand", "name": "Genre"}]
    assert nz.tag_types_from_body(None) == []


def test_crawl_collects_namespaces_and_tags(tmp_path):
    async def go():
        async with client(tmp_path) as c:
            return await T.crawl(c, ["brand"], max_pages=3, seeds=["skincare"])
    r = run_async(go())["brand"]
    assert [t["id"] for t in r["types"]] == ["urn:tag:genre:brand", "urn:tag:style:qloo"]
    g = r["namespaces"]["urn:tag:genre:brand"]
    assert g["complete"] and g["count"] >= 3 and any(t["name"] == "Health & Beauty" for t in g["tags"])


def test_crawl_detects_ignored_paging(tmp_path):
    def handler(req):
        if req.url.path == "/v2/tags/types":
            return httpx.Response(200, json={"results": {"tag_types": [{"id": "urn:tag:genre:brand", "name": "Genre"}]}})
        tags = [{"id": f"urn:tag:genre:brand:c{i}", "name": f"C{i}"} for i in range(3)]  # same page every time
        return httpx.Response(200, json={"results": {"tags": tags}})
    async def go():
        async with client(tmp_path, httpx.MockTransport(handler)) as c:
            return await T.crawl(c, ["brand"], max_pages=4, take=3)
    ns = run_async(go())["brand"]["namespaces"]["urn:tag:genre:brand"]
    assert ns["paging_works"] is False and ns["pages"] == 2 and ns["count"] == 3


def test_category_tree():
    tags = [{"id": "urn:tag:genre:brand:health_and_beauty", "name": "HB"}, {"id": "urn:tag:genre:brand:health_and_beauty:skincare", "name": "S"},
            {"id": "urn:tag:genre:brand:retail", "name": "R"}]
    assert T.category_tree(tags) == {"health_and_beauty": ["skincare"], "retail": []}


def test_probe_category_reports_whether_brands_carry_the_category(tmp_path):
    async def go():
        async with client(tmp_path) as c:
            return await T.probe_category(c, ["skincare"], ["urn:tag:genre:brand:mock_category"], ["Nivea"], "Lagos", take=3)
    r = run_async(go())
    m = r["categories"]["urn:tag:genre:brand:mock_category"]["hard_filter_with_location"]
    assert m["ok"] and all(b["carries_category"] for b in m["brands"]) and r["related"]["Nivea"]["anchor"]
    assert "Category probe" in T.probe_markdown(r)


def test_cli_taxonomy_and_probe_mock(tmp_path, capsys):
    assert main(["taxonomy", "--mock", "--out", str(tmp_path), "--no-zip", "--pages", "2"]) == 0
    assert "Brand categories" in capsys.readouterr().out
    assert main(["category-probe", "--mock", "--out", str(tmp_path), "--no-zip", "--search", "skincare", "--entity", "Nivea"]) == 0
    assert "Related brands for Nivea" in capsys.readouterr().out


def test_cli_probe_needs_something_to_probe(tmp_path):
    with pytest.raises(SystemExit):
        main(["category-probe", "--mock", "--out", str(tmp_path), "--no-zip"])


def test_priority_types_reaches_brand_genre_even_when_it_is_far_down_the_alphabet():
    types = [{"id": f"urn:tag:aaa{i}:qloo"} for i in range(30)] + [{"id": "urn:tag:genre:brand"}, {"id": "urn:tag:industry:qloo"}]
    got = [t["id"] for t in T.priority_types("brand", types, limit=5)]
    assert got[:2] == ["urn:tag:genre:brand", "urn:tag:industry:qloo"] and len(got) == 5
