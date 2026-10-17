"""The exploring agent: tools filter Qloo responses, the loop keeps the prompt small, and the final check drops anything
the calls do not support."""

import json

import httpx

from discover.agent import tools as T
from discover.agent.loop import run_agent, validate_finish
from discover.personas.intake import ProductIntake
from tests.test_personas_categories import CASES, _client
from tests.test_personas_step2 import run_async

BRAND = {"id": "urn:tag:genre:brand:health_and_beauty:oral_care", "name": "Oral care", "type": "urn:tag:genre:brand"}


def handler_factory(log, fail_weights=False):
    def handler(req):
        p, q = req.url.path, dict(req.url.params)
        log.append((p, q))
        if p == "/search":
            n = q["query"]
            return httpx.Response(200, json={"results": [{"entity_id": f"id-{n}", "name": n, "types": ["urn:entity:brand"], "popularity": 0.5,
                                                          "tags": [BRAND, {"id": "urn:tag:industry:qloo:oral_care", "name": "Oral care"}]}]})
        if p == "/entities":
            return httpx.Response(200, json={"results": [{"name": "x", "tags": [
                BRAND, {"id": "urn:tag:competitor_brand:qloo:sensodyne", "name": "Sensodyne"},
                {"id": "urn:tag:customer_segment:qloo:families", "name": "Families"}]}]})
        if p == "/v2/tags":
            return httpx.Response(200, json={"results": {"tags": [{"id": BRAND["id"], "name": "Oral care", "type": "urn:tag:genre:brand"}]}})
        if p == "/v2/insights" and q.get("filter.type") == "urn:entity:brand":
            if fail_weights and any(k.endswith(".weight") for k in q):
                return httpx.Response(400, json={"error": "bad"})
            return httpx.Response(200, json={"results": {"entities": [
                {"entity_id": f"id-peer{i}", "name": f"Peer{i}", "popularity": 0.3, "tags": [BRAND], "query": {"affinity": 0.9}} for i in range(3)]}})
        if p == "/v2/insights" and q.get("filter.type") == "urn:demographics":
            return httpx.Response(200, json={"results": {"demographics": [{"query": {"age": {"35_to_44": 0.5}, "gender": {"male": 0.1}}}]}})
        return httpx.Response(404, json={})
    return handler


class ScriptedLLM:
    def __init__(self, turns):
        self.turns, self.prompts, self.calls = list(turns), [], 0

    async def chat_json(self, name, system, user, **kw):
        self.calls += 1
        self.prompts.append(user)
        if not self.turns:
            raise RuntimeError("script exhausted")
        return self.turns.pop(0)


def act(tool, **args):
    return {"goal": "g", "notebook": "n", "action": {"tool": tool, "args": args}}


def intake():
    return ProductIntake(**CASES["toothpaste"])


def run(tmp_path, turns, steps=10, **hk):
    log = []
    llm = ScriptedLLM(turns)

    async def go():
        async with _client(tmp_path, httpx.MockTransport(handler_factory(log, **hk))) as c:
            tb = T.Toolbox(c, "Lagos")
            return await run_agent(llm, tb, intake(), None, max_steps=steps), tb
    out, tb = run_async(go())
    return out, tb, log, llm


def test_agent_explores_then_finishes_with_cited_competitors(tmp_path):
    out, tb, log, llm = run(tmp_path, [
        act("search_entity", query="Colgate"),
        act("entity_record", entity_id="id-Colgate"),
        act("insights", kind="brand", filter_tags=["genre:brand:health_and_beauty:oral_care"], interest_entities=["id-Colgate"]),
        {"finish": {"competitors": [{"name": "Peer0", "entity_id": "id-peer0", "why": "same category, similar audience", "cites": ["Q03"]}],
                    "findings": [{"claim": "Qloo lists Sensodyne as a competitor of Colgate", "cites": ["Q02"]}], "gaps": ["no price data"]}}])
    r = out["result"]
    assert [c["name"] for c in r["competitors"]] == ["Peer0"] and r["findings"][0]["cites"] == ["Q02"] and not r["rejected"]
    ins = [q for p, q in log if p == "/v2/insights"][0]
    assert ins["filter.tags"] == "urn:tag:genre:brand:health_and_beauty:oral_care" and ins["signal.interests.entities"] == "id-Colgate"
    assert len(out["ledger"]) == 3 and out["trace"][-1].get("finish")


def test_checker_drops_invented_ids_and_uncited_claims(tmp_path):
    out, tb, _, _ = run(tmp_path, [
        act("search_entity", query="Colgate"),
        {"finish": {"competitors": [{"name": "Invented", "entity_id": "zzz", "why": "x", "cites": ["Q01"]},
                                    {"name": "Colgate", "entity_id": "id-Colgate", "why": "x", "cites": ["Q99"]}],
                    "findings": [{"claim": "Nigerians love it", "cites": []}, {"claim": "ok", "cites": ["Q01"]}],
                    "audience_hints": [{"label": "a", "ages": ["25_to_29"], "claim": "c", "cites": ["Q42"]}]}}])
    r = out["result"]
    assert r["competitors"] == [] and [f["claim"] for f in r["findings"]] == ["ok"] and r["audience_hints"] == []
    assert len(r["rejected"]) == 4


def test_unknown_tool_and_bad_args_become_observations_not_crashes(tmp_path):
    out, tb, _, llm = run(tmp_path, [act("hack_the_planet"), act("entity_record"), {"finish": {"gaps": ["x"]}}])
    assert [e["ok"] for e in out["ledger"]] == [False, False]
    assert "unknown tool" in llm.prompts[1] and out["result"]["gaps"] == ["x"]


def test_running_out_of_steps_still_returns_what_was_found(tmp_path):
    out, tb, _, _ = run(tmp_path, [act("search_entity", query="a"), act("search_entity", query="b")], steps=2)
    assert out["result"]["competitors"] == [] and "ran out of steps" in out["result"]["gaps"][0] and len(out["ledger"]) == 2


def test_llm_failure_ends_exploration_gracefully(tmp_path):
    out, tb, _, _ = run(tmp_path, [act("search_entity", query="a")])  # script exhausted on step 2
    assert out["trace"][-1]["error"].startswith("LLM failed") and out["result"]["gaps"]


def test_prompt_stays_small_over_many_steps(tmp_path):
    turns = [act("search_entity", query=f"brand{i}") for i in range(12)] + [{"finish": {}}]
    out, tb, _, llm = run(tmp_path, turns, steps=14)
    assert max(len(p) for p in llm.prompts) < 9000


def test_weights_operator_and_location_params_are_sent_and_weights_fall_back(tmp_path):
    out, tb, log, _ = run(tmp_path, [
        act("insights", kind="brand", filter_tags=["a:b", "c:d"], filter_operator="intersection", interest_entities=["e1"],
            weights={"interests.entities": "high"}),
        {"finish": {}}], fail_weights=True)
    ins = [q for p, q in log if p == "/v2/insights"]
    assert ins[0]["operator.filter.tags"] == "intersection" and ins[0]["signal.interests.entities.weight"] == "high"
    assert not any(k.endswith(".weight") for k in ins[-1]) and "weights were rejected" in json.dumps(out["ledger"][0]["observation"])


def test_find_tags_and_entity_record_output_is_grouped_and_short(tmp_path):
    out, tb, _, _ = run(tmp_path, [act("find_tags", query="toothpaste"), act("entity_record", entity_id="id-x"), {"finish": {}}])
    tags = out["ledger"][0]["observation"]["tags"][0]
    assert tags["id"] == "genre:brand:health_and_beauty:oral_care"  # short form; urn prefix is added back on use
    rec = out["ledger"][1]["observation"]["tags"]
    assert rec["competitor_brand"] == ["Sensodyne"] and rec["customer_segment"] == ["Families"]


def test_validate_finish_requires_entity_to_have_been_seen():
    class TB:  # minimal stand-in
        class ledger:
            @staticmethod
            def ids(): return {"Q01"}
            seen_entities = {"e1": {"name": "Real"}}
    r = validate_finish({"competitors": [{"name": "Real", "entity_id": "e1", "cites": ["Q01"]}]}, TB)
    assert r["competitors"][0]["name"] == "Real"


def test_clip_shortens_big_observations():
    big = {"entities": [{"id": str(i), "name": "x" * 40} for i in range(200)]}
    assert len(json.dumps(T.clip(big))) <= T.MAX_OBS_CHARS + 200


def test_runner_with_agent_uses_checked_competitors_and_writes_trace(make_intake, store, tmp_path):
    from tests.test_personas_step2 import LLM_SETTINGS, fake_llm_transport, opts
    from discover.personas.runner import execute_personas
    inner, seen = fake_llm_transport()
    agent_turns = [act("search_entity", query="Crest"),
                   {"finish": {"competitors": [{"name": "Crest", "entity_id": "x", "why": "w", "cites": ["Q01"]}],
                               "findings": [{"claim": "Crest resolves to a toothpaste brand", "cites": ["Q01"]}],
                               "gaps": ["no price data"]}}]
    state = {"i": 0}

    def handler(req):
        body = json.loads(req.content)
        if body["messages"][0]["content"].startswith("You are a market-research agent"):
            turn = agent_turns[min(state["i"], len(agent_turns) - 1)]
            state["i"] += 1
            if state["i"] == 2:  # use the real id the mock search returned
                payload = json.loads(body["messages"][1]["content"])
                eid = payload["last_result"]["result"]["entities"][0]["id"]
                turn = json.loads(json.dumps(turn).replace('"x"', json.dumps(eid)))
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(turn)}}]})
        return inner.handle_request(req)

    o = opts(make_intake, tmp_path)
    o.agent, o.agent_steps = True, 6
    code, run, summary = run_async(execute_personas(o, LLM_SETTINGS, store, llm_transport=httpx.MockTransport(handler)))
    res = json.loads((run / "04_personas.json").read_text())
    assert res["agent"]["competitors"] and res["agent"]["findings"][0]["cites"] == ["Q01"]
    assert (run / "agent" / "trace.json").exists() and (run / "agent" / "ledger.json").exists()
    md = (run / "04_personas.md").read_text()
    assert "What the exploring agent found in Qloo" in md and "[Q01]" in md and "Could not establish: no price data" in md
