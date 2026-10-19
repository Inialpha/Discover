"""Model fallback chain: a failing or quota-exhausted model hands over to the next one, per call."""

import json
from dataclasses import replace

import httpx

from discover.engine.llm.client import LLMClient, LLMError
from discover.engine.recorder import RunRecorder
from tests.test_personas_step2 import LLM_SETTINGS, run_async

S = replace(LLM_SETTINGS, llm_model="main", llm_fallback_models=("backup", "last"))
OK = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"ok": 1})}}]}


def client(tmp_path, behaviour):
    seen = []

    def handler(req):
        model = json.loads(req.content)["model"]
        seen.append(model)
        return behaviour(model)
    llm = LLMClient(S, RunRecorder(tmp_path / "r"), transport=httpx.MockTransport(handler))
    llm._sleep = lambda s: _noop()
    return llm, seen


async def _noop():
    return None


def test_failing_main_model_falls_back_for_that_call_only(tmp_path):
    state = {"n": 0}

    def beh(model):
        if model == "main":
            state["n"] += 1
            return httpx.Response(400 if state["n"] > 99 else 500, json={"error": "down"}) if state["n"] <= 3 else httpx.Response(200, json=OK)
        return httpx.Response(200, json=OK)
    llm, seen = client(tmp_path, beh)
    assert run_async(llm.chat_json("a", "s", "u")) == {"ok": 1}
    assert seen[-1] == "backup" and llm.fallbacks_used == 1
    assert run_async(llm.chat_json("b", "s", "u")) == {"ok": 1}  # main is tried again on the next call and recovers
    assert seen[-1] == "main" and llm.model_calls["main"] == 1


def test_daily_quota_of_one_model_skips_it_from_then_on(tmp_path):
    def beh(model):
        if model == "main":
            return httpx.Response(429, json={"error": {"message": "Rate limit reached on tokens per day (TPD): Limit 200000"}})
        return httpx.Response(200, json=OK)
    llm, seen = client(tmp_path, beh)
    assert run_async(llm.chat_json("a", "s", "u")) == {"ok": 1}
    assert "main" in llm.exhausted and llm.daily_exhausted is None
    n = len(seen)
    run_async(llm.chat_json("b", "s", "u"))
    assert seen[n:] == ["backup"]  # main not called again


def test_all_models_exhausted_reports_daily_limit_and_stops_calling(tmp_path):
    def beh(model):
        return httpx.Response(429, json={"error": {"message": "tokens per day (TPD) limit"}})
    llm, seen = client(tmp_path, beh)
    try:
        run_async(llm.chat_json("a", "s", "u"))
        raise AssertionError("expected LLMError")
    except LLMError:
        pass
    assert llm.daily_exhausted and set(llm.exhausted) == {"main", "backup", "last"}
    n = len(seen)
    try:
        run_async(llm.chat_json("b", "s", "u"))
    except LLMError as e:
        assert "daily token limit" in str(e)
    assert len(seen) == n


def test_no_fallback_configured_behaves_as_before(tmp_path):
    llm = LLMClient(replace(LLM_SETTINGS, llm_fallback_models=()), RunRecorder(tmp_path / "r"),
                    transport=httpx.MockTransport(lambda req: httpx.Response(200, json=OK)))
    assert llm.models == [LLM_SETTINGS.llm_model] and run_async(llm.chat_json("a", "s", "u")) == {"ok": 1}
