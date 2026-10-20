from discover.engine.personas import avatar, identity


def test_enrich_prefers_segment_gender_then_llm_then_alternates():
    p = identity.enrich({"name": "Saver", "headline": "h", "first_name": "Ngozi", "gender": "male"}, "s1", "female", ["35_to_44"], 1)
    assert p["gender"] == "female" and p["gender_basis"] == "segment" and p["display_name"] == "Ngozi" and p["name_basis"] == "llm"
    p = identity.enrich({"name": "x", "gender": "male"}, "s1", None, ["25_to_29"], 1)
    assert p["gender"] == "male" and p["gender_basis"] == "illustrative"
    a = identity.enrich({"name": "x"}, "s1", None, ["25_to_29"], 1)["gender"]
    b = identity.enrich({"name": "x"}, "s1", None, ["25_to_29"], 2)["gender"]
    assert {a, b} == {"male", "female"}


def test_bad_first_names_fall_back_to_generated():
    for bad in ("", "Dr. Strange 3", "<script>", "A", None, "x" * 40):
        p = identity.enrich({"name": "x", "first_name": bad}, "s1", "male", ["30_to_34"], 1)
        assert p["name_basis"] == "generated" and p["display_name"] in identity.MALE


def test_avatar_key_age_label_and_title_summary():
    p = identity.enrich({"name": "Title", "headline": "Short"}, "s1", "female", ["30_to_34", "35_to_44"], 2)
    assert p["avatar"].startswith("f-") and p["title"] == "Title" and p["summary"] == "Short"
    assert identity.age_label(["30_to_34", "35_to_44"]) == "30–44" and identity.age_label(["55_and_older"]) == "55+"
    assert identity.age_label(["24_and_younger", "25_to_29"]).startswith("under 25")


def test_avatar_svg_and_png_are_valid_and_differ_by_gender():
    s_f, s_m = avatar.svg("f-40-2"), avatar.svg("m-40-2")
    assert s_f.startswith("<svg") and s_f != s_m and "<rect" in s_f
    data = avatar.png("f-40-2", 64)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert avatar.svg("garbage")  # unknown keys still render a neutral avatar


def test_older_age_greys_the_hair():
    assert avatar.GREY in avatar.svg("m-62-0") and avatar.GREY not in avatar.svg("m-30-0")


def test_runner_reports_progress_and_personas_carry_identity(make_intake, store, tmp_path):
    from discover.engine.personas.runner import PersonaOptions, execute_personas
    from tests.test_personas_step2 import QLOO_SETTINGS, run_async
    import json
    events = []
    o = PersonaOptions(intake=make_intake(price=40_000, competitors=["Tecno"], max_personas=3), out=tmp_path / "runs", mock=True, zip=False,
                       progress=lambda stage, msg, data: events.append((stage, msg)))
    code, run, summary = run_async(execute_personas(o, QLOO_SETTINGS, store))
    stages = [e[0] for e in events]
    assert stages[0] == "affordability" and "competitors" in stages and "personas" in stages and stages[-1] == "report"
    res = json.loads((run / "04_personas.json").read_text())
    p = res["personas"][0]
    assert p["display_name"] and p["gender"] in ("male", "female") and p["avatar"] and p["title"] and p["age_label"]


def test_a_failing_progress_callback_never_breaks_a_run(make_intake, store, tmp_path):
    from discover.engine.personas.runner import PersonaOptions, execute_personas
    from tests.test_personas_step2 import QLOO_SETTINGS, run_async

    def boom(*a):
        raise RuntimeError("x")
    o = PersonaOptions(intake=make_intake(price=40_000, competitors=["Tecno"], max_personas=2), out=tmp_path / "runs", mock=True, zip=False, progress=boom)
    code, run, summary = run_async(execute_personas(o, QLOO_SETTINGS, store))
    assert code == 0
