"""The exploring agent: tools filter Qloo responses, the loop keeps the prompt small, and the final check drops anything
the calls do not support."""

import json

import httpx

from discover.engine.agent import tools as T
from discover.engine.agent.loop import run_agent, validate_finish
from discover.engine.personas.intake import ProductIntake
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


def run(tmp_path, turns, steps=10, min_calls=0, min_comps=0, **hk):
    from discover.engine.agent import loop as L
    L.MIN_GOOD_CALLS = min_calls
    L.MIN_COMPETITORS = min_comps
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
    # an entity a call really returned is accepted even when its cite is garbled (evidence = the call that returned it)
    assert [(c["name"], c["cites"]) for c in r["competitors"]] == [("Colgate", ["Q01"])]
    assert [f["claim"] for f in r["findings"]] == ["ok"] and r["audience_hints"] == []
    assert len(r["rejected"]) == 3


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
    from discover.engine.personas.runner import execute_personas
    from discover.engine.agent import loop as L
    L.MIN_GOOD_CALLS = 0
    L.MIN_COMPETITORS = 0
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


def test_finishing_before_exploring_is_refused(tmp_path):
    from discover.engine.agent import loop as L
    out, tb, _, llm = run(tmp_path, [{"finish": {"gaps": ["GlowSkin not found"]}}, act("find_tags", query="skin cream"),
                                     act("search_entity", query="Nivea"), act("entity_record", entity_id="id-Nivea"),
                                     act("find_tags", query="cream"), {"finish": {"gaps": []}}], min_calls=4)
    L.MIN_GOOD_CALLS = 0
    assert out["trace"][0].get("refused_finish") and "cannot finish yet" in llm.prompts[1] and len(out["ledger"]) == 4


def test_template_placeholders_are_rejected_with_a_clear_error(tmp_path):
    out, tb, _, llm = run(tmp_path, [act("insights", kind="brand", filter_tags=["{{Q03.tag_ids[0]}}"]), {"finish": {}}])
    assert out["ledger"][0]["ok"] is False and "literal values" in out["ledger"][0]["error"]


def test_unknown_insights_args_are_reported_not_ignored(tmp_path):
    out, tb, _, _ = run(tmp_path, [act("insights", kind="brand", filter_tag_ids=["a"]), {"finish": {}}])
    assert out["ledger"][0]["ok"] is False and "filter_tag_ids" in out["ledger"][0]["error"] and "filter_tags" in out["ledger"][0]["error"]


def test_repeating_the_same_failing_call_is_called_out(tmp_path):
    out, tb, _, llm = run(tmp_path, [act("hack"), act("hack"), {"finish": {}}])
    assert "exact failing call" in llm.prompts[2]


def test_rate_limit_is_waited_out_not_fatal(tmp_path):
    from discover.engine.agent import loop as L
    waits = []

    class Flaky(ScriptedLLM):
        n = 0

        async def chat_json(self, name, system, user, **kw):
            Flaky.n += 1
            if Flaky.n == 1:
                raise RuntimeError("HTTP 429")
            return await super().chat_json(name, system, user, **kw)

    async def fake_sleep(x):
        waits.append(x)

    async def go():
        async with _client(tmp_path, httpx.MockTransport(handler_factory([]))) as c:
            return await run_agent(Flaky([{"finish": {"gaps": ["x"]}}]), T.Toolbox(c, "Lagos"), intake(), None, max_steps=3, sleep=fake_sleep)
    L.MIN_GOOD_CALLS = 0
    L.MIN_COMPETITORS = 0
    out = run_async(go())
    assert waits == [L.RATE_LIMIT_WAIT] and out["result"]["gaps"] == ["x"]


def test_name_only_competitor_is_matched_to_a_seen_entity(tmp_path):
    out, tb, _, _ = run(tmp_path, [act("search_entity", query="Crest"),
                                   {"finish": {"competitors": [{"name": "crest", "entity_id": "", "why": "w"}]}}])
    assert out["result"]["competitors"][0]["entity_id"] == "id-Crest"


def test_harmless_argument_slips_are_absorbed_and_reported(tmp_path):
    out, tb, log, llm = run(tmp_path, [act("search_entity", query="Crest", limit=5, location="Lagos", namespace="brand"),
                                       act("audience_demographics", entity_id="id-Crest"), {"finish": {}}])
    assert [e["ok"] for e in out["ledger"]] == [True, True]
    assert "ignored arguments" in llm.prompts[1]
    demo = [q for p, q in log if p == "/v2/insights" and q.get("filter.type") == "urn:demographics"][0]
    assert demo["signal.interests.entities"] == "id-Crest"


def test_known_memory_lists_seen_entities_in_every_prompt(tmp_path):
    out, tb, _, llm = run(tmp_path, [act("search_entity", query="Crest"), act("find_tags", query="toothpaste"), {"finish": {}}])
    assert "id-Crest" in llm.prompts[2] and "genre:brand:health_and_beauty:oral_care" in llm.prompts[2]


def test_noise_tag_namespaces_are_dropped_from_observations():
    g = T.group_tags([{"id": "urn:tag:aesthetic_property:qloo:clinical"}, {"id": "urn:tag:lifestyle:qloo:x"},
                      {"id": "urn:tag:industry:qloo:oral_care", "name": "Oral care"},
                      {"id": "urn:tag:genre:brand:health_and_beauty"}])
    assert set(g) == {"industry", "genre:brand"}


def test_vet_anchors_drops_wrong_businesses(tmp_path):
    from discover.engine.personas import competitors as C
    from tests.test_personas_categories import _broad_handler

    def handler(req):
        if req.url.path == "/entities":
            return httpx.Response(200, json={"results": [{"name": "x", "tags": [{"id": "urn:tag:industry:qloo:higher_education", "name": "Higher Education"}]}]})
        return httpx.Response(404, json={})

    class Judge:
        async def chat_json(self, *a, **k):
            return {"matches": {"Colgate": False}}

    async def go():
        async with _client(tmp_path, httpx.MockTransport(handler)) as c:
            return await C.vet_anchors(c, intake(), [{"name": "Colgate", "entity_id": "e1"}], Judge())
    kept, notes, profiles = run_async(go())
    assert kept == [] and "Higher Education" in notes[0]


def test_help_tool_serves_reference_without_a_qloo_call(tmp_path):
    out, tb, log, _ = run(tmp_path, [act("qloo_help", topic="recipes"), act("qloo_help", topic="nonsense"), {"finish": {}}])
    assert "filter_tags" in out["ledger"][0]["observation"]["text"] and "Unknown topic" in out["ledger"][1]["observation"]["text"]
    assert log == []


def test_help_is_not_counted_as_exploration(tmp_path):
    out, tb, _, llm = run(tmp_path, [act("qloo_help"), {"finish": {"gaps": ["x"]}}, act("find_tags", query="a"), act("find_tags", query="b"),
                                     act("find_tags", query="c"), act("find_tags", query="d"), {"finish": {}}], min_calls=4)
    from discover.engine.agent import loop as L
    L.MIN_GOOD_CALLS = 0
    assert out["trace"][1].get("refused_finish")


def test_reference_names_every_parameter_the_insights_tool_accepts():
    from discover.engine.agent.reference import SECTIONS
    text = " ".join(SECTIONS.values())
    for name in ("filter_tags", "filter_operator", "interest_entities", "interest_tags", "weights", "exclude_tags", "audiences", "use_location"):
        assert name in text, name
    for band in ("24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"):
        assert band in SECTIONS["demographics"]


def test_exclude_tags_and_audiences_reach_the_request(tmp_path):
    out, tb, log, _ = run(tmp_path, [act("insights", kind="brand", filter_tags=["a:b"], exclude_tags=["c:d"], audiences=["urn:audience:life_stage"]), {"finish": {}}])
    q = [q for p, q in log if p == "/v2/insights"][0]
    assert q["filter.exclude.tags"] == "urn:tag:c:d" and q["signal.demographics.audiences"] == "urn:audience:life_stage"


def _daily_429():
    return {"error": {"message": "Rate limit reached for model x on tokens per day (TPD): Limit 200000, Used 199705, Requested 2307."}}


def test_daily_token_limit_fails_fast_without_retries_and_sticks():
    from discover.engine.llm.client import LLMClient, LLMError
    from discover.engine.recorder import RunRecorder
    from tests.test_personas_step2 import LLM_SETTINGS
    import tempfile, pathlib
    n = {"c": 0}

    def h(req):
        n["c"] += 1
        return httpx.Response(429, json=_daily_429(), headers={"retry-after": "5"})
    llm = LLMClient(LLM_SETTINGS, RunRecorder(pathlib.Path(tempfile.mkdtemp())), transport=httpx.MockTransport(h))
    for _ in range(2):
        try:
            run_async(llm.chat_json("x", "s", "u"))
            assert False
        except LLMError as e:
            assert "daily token limit" in str(e)
    assert n["c"] == 1 and llm.daily_exhausted


def test_agent_stops_immediately_on_daily_limit(tmp_path):
    from discover.engine.llm.client import LLMError

    class Dead(ScriptedLLM):
        async def chat_json(self, *a, **k):
            self.calls += 1
            raise LLMError("daily token limit reached (x)")
    log, llm = [], Dead([])

    async def go():
        async with _client(tmp_path, httpx.MockTransport(handler_factory(log))) as c:
            return await run_agent(llm, T.Toolbox(c, "Lagos"), intake(), None, max_steps=5)
    out = run_async(go())
    assert llm.calls == 1 and "daily token limit" in out["trace"][0]["error"]


def test_agent_llm_settings_override():
    from tests.test_personas_step2 import LLM_SETTINGS
    from dataclasses import replace
    s = replace(LLM_SETTINGS, agent_llm_model="other-model")
    assert s.for_agent().llm_model == "other-model" and s.for_agent().llm_api_key == LLM_SETTINGS.llm_api_key
    assert LLM_SETTINGS.for_agent() == LLM_SETTINGS


def test_use_location_on_search_is_absorbed(tmp_path):
    out, tb, _, _ = run(tmp_path, [act("search_entity", query="Crest", use_location=False), {"finish": {}}])
    assert out["ledger"][0]["ok"] is True


def test_finishing_without_verified_competitors_is_refused_with_a_concrete_next_step(tmp_path):
    from discover.engine.agent import loop as L
    out, tb, _, llm = run(tmp_path, [act("find_tags", query="toothpaste"), act("search_entity", query="Pepsodent"),
                                     {"finish": {"gaps": ["lazy"]}},
                                     act("entity_record", entity_id="id-Pepsodent"),
                                     {"finish": {"competitors": [{"name": "Pepsodent", "entity_id": "id-Pepsodent"}, {"name": "Colgate", "entity_id": "id-Pepsodent"}]}},
                                     {"finish": {"gaps": ["still lazy"]}}], min_comps=2, steps=8)
    L.MIN_COMPETITORS = 0
    assert out["trace"][2].get("refused_finish") and "entity_record" in llm.prompts[3] and "Pepsodent" in llm.prompts[3]


def test_refusals_are_capped_so_the_agent_cannot_loop_forever(tmp_path):
    from discover.engine.agent import loop as L
    out, tb, _, _ = run(tmp_path, [act("find_tags", query="a")] + [{"finish": {"gaps": ["x"]}}] * 6, min_comps=2, steps=10)
    L.MIN_COMPETITORS = 0
    assert sum(1 for t in out["trace"] if t.get("refused_finish")) == 3 and out["trace"][-1].get("finish")


def test_next_step_hint_walks_the_recipe(tmp_path):
    from discover.engine.agent.loop import next_step_hint
    out, tb, _, _ = run(tmp_path, [{"finish": {}}])
    assert "find_tags" in next_step_hint(tb, intake())
