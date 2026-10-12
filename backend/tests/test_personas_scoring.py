import pytest
from discover.personas.affordability import assess
from discover.personas.refdata.records import GNI_PC_LCU, RefRecord
from discover.personas.refdata.store import ReferenceStore
from discover.personas.scoring import (WEIGHTS, keyword_hits, score_segments, taste_scores_from_affinities)
from discover.personas.segments import ALL_CATEGORIES, ALL_TIERS, SEGMENTS, by_id, candidates


def run(make_intake, store, taste=None, **kw):
    i = make_intake(**kw)
    a = assess(i, store)
    return i, a, score_segments(i, a, taste)


def ids(res):
    return [s.id for s in res.ranked]


# ---- the no-tier-is-privileged guarantees ----------------------------------------------------------------
@pytest.mark.parametrize("category", ALL_CATEGORIES)
@pytest.mark.parametrize("tier", ALL_TIERS)
def test_every_category_has_segments_at_every_tier(category, tier):
    assert candidates(category, tier), f"no rule covers {category} at {tier}"


def test_segment_ids_unique_and_fields_valid():
    from discover.personas.segments import AGES
    assert len({s.id for s in SEGMENTS}) == len(SEGMENTS)
    for s in SEGMENTS:
        assert set(s.ages) <= set(AGES) and set(s.quintiles) <= {1, 2, 3, 4, 5}
        assert set(s.tiers) <= set(ALL_TIERS) and set(s.categories) <= set(ALL_CATEGORIES)
        assert s.basis == "rule" and s.keywords


def test_budget_and_premium_phones_get_different_personas(make_intake, store):
    _, a1, budget = run(make_intake, store, price=40_000, max_personas=10)
    _, a2, premium = run(make_intake, store, price=1_500_000, max_personas=10)
    assert a1.tier == "budget" and a2.tier == "premium"
    assert set(ids(budget)) != set(ids(premium))
    assert "first_time_users" in ids(budget) and "first_time_users" not in ids(premium)
    assert "high_earners_young" in ids(premium) and "high_earners_young" not in ids(budget)


def test_budget_product_gets_budget_segments_ranked_first(make_intake, store):
    _, _, res = run(make_intake, store, price=40_000)
    assert res.ranked[0].id in {"students_budget", "first_time_users", "cost_conscious_households"}
    assert res.ranked[0].confidence == "medium"


def test_mass_market_product_has_its_own_segments(make_intake, store):
    _, a, res = run(make_intake, store, price=150_000, max_personas=10)
    assert a.tier == "mass"
    assert {"early_career", "students_budget"} <= set(ids(res))


def test_premium_product_in_low_income_market_ranks_top_bands_first(make_intake, store):
    _, a, res = run(make_intake, store, price=1_500_000, max_personas=10)
    sc = {s.id: s for s in res.ranked}
    assert a.tier == "premium"
    assert sc["high_earners_young"].components["affordability"]["value"] == pytest.approx(0.25)
    assert sc["students_supported"].components["affordability"]["value"] < sc["high_earners_young"].components["affordability"]["value"]
    assert all(s.components["affordability"]["value"] <= 0.5 for s in res.ranked)


def test_all_out_of_reach_segments_are_excluded_with_reason(make_intake, store):
    store.put_many([RefRecord("NGA", GNI_PC_LCU, 2025, 100_000.0, "t", "2026-01-01T00:00:00+00:00")])
    i, a, res = run(make_intake, store, category="vehicle", price=5_000_000, max_personas=10)
    assert a.tier == "premium"
    assert res.ranked == []
    assert any("out of reach" in e["reason"] for e in res.excluded)


def test_tier_mismatch_is_listed_as_excluded(make_intake, store):
    _, _, res = run(make_intake, store, price=40_000, max_personas=10)
    reasons = {e["id"]: e["reason"] for e in res.excluded}
    assert "high_earners_young" in reasons and "rule:" in reasons["high_earners_young"]


# ---- components -------------------------------------------------------------------------------------------
def test_affordability_component_values(make_intake, store):
    _, _, res = run(make_intake, store, price=600_000, max_personas=10)
    he = next(s for s in res.ranked if s.id == "high_earners_young")  # bands 4,5 -> stretch, comfortable
    assert he.components["affordability"]["value"] == pytest.approx(0.75)
    assert he.reach == {4: "stretch", 5: "comfortable"}


def test_feature_keywords_boost_ranking(make_intake, store):
    _, _, plain = run(make_intake, store, price=150_000, description="A phone for general daily use by most people.",
                      max_personas=10)
    _, _, gaming = run(make_intake, store, price=150_000, description="A phone with a fast processor and graphics.",
                       features=["gaming mode", "high refresh rate"], max_personas=10)
    sp = {s.id: s.score for s in plain.ranked}
    sg = {s.id: s.score for s in gaming.ranked}
    assert sg["gamers"] > sp["gamers"]
    assert next(s for s in gaming.ranked if s.id == "gamers").matched_keywords


def test_keyword_hits_whole_words_only():
    seg = by_id("gamers")
    assert keyword_hits(seg, "this is a gaming phone") == ["gaming"]
    assert keyword_hits(seg, "engaged gamer") == []  # 'game'/'gaming' are not substrings of other words here
    assert keyword_hits(by_id("tech_enthusiasts"), "supports 5g and has ai") == ["5g", "ai"]


def test_taste_component_is_optional_and_renormalised(make_intake, store):
    # budget phone: 9 candidate segments, so every one fits inside max_personas=10
    _, _, base = run(make_intake, store, price=40_000, max_personas=10)
    taste = {"first_time_users": 1.0, "students_budget": 0.0}
    _, _, withtaste = run(make_intake, store, taste, price=40_000, max_personas=10)
    b = next(s for s in base.ranked if s.id == "first_time_users")
    t = next(s for s in withtaste.ranked if s.id == "first_time_users")
    assert "taste_fit" not in b.components and "taste_fit" in t.components
    assert t.score > b.score
    s2 = next(s for s in withtaste.ranked if s.id == "students_budget")
    assert s2.components["taste_fit"]["value"] == 0.0
    base_students = next(s for s in base.ranked if s.id == "students_budget")
    assert s2.score < base_students.score
    # a segment without taste data is scored on the remaining components only
    other = next(s for s in withtaste.ranked if s.id not in taste)
    assert "taste_fit" not in other.components
    assert "taste" in withtaste.ranked_by


def test_score_is_weighted_mean_of_available_components(make_intake, store):
    _, _, res = run(make_intake, store, price=40_000, max_personas=10)
    for s in res.ranked:
        tw = sum(c["weight"] for c in s.components.values())
        expect = sum(c["value"] * c["weight"] for c in s.components.values()) / tw
        assert s.score == pytest.approx(expect, abs=1e-3)
        assert set(s.components) <= set(WEIGHTS)


def test_taste_scores_from_affinities():
    out = taste_scores_from_affinities({"a": [0.5, 1.5], "b": [], "c": [0.2, None, "x"], "d": [-1.0]})
    assert out == {"a": 1.0, "c": 0.2, "d": 0.0}


def test_confidence_is_never_high(make_intake, store):
    for price in (40_000, 150_000, 600_000, 1_500_000):
        _, _, res = run(make_intake, store, taste={s.id: 0.9 for s in SEGMENTS}, price=price, max_personas=10)
        assert {s.confidence for s in res.ranked} <= {"low", "medium"}


# ---- limits and filters -----------------------------------------------------------------------------------
@pytest.mark.parametrize("n", [1, 3, 6, 10])
def test_max_personas_caps_and_reports_omitted(make_intake, store, n):
    _, _, res = run(make_intake, store, price=150_000, max_personas=n)
    assert len(res.ranked) <= n
    full = run(make_intake, store, price=150_000, max_personas=10)[2]
    total = len(full.ranked) + full.omitted_by_limit
    assert len(res.ranked) + res.omitted_by_limit == total


def test_age_focus_filters(make_intake, store):
    _, _, res = run(make_intake, store, price=150_000, age_focus=["55_and_older"], max_personas=10)
    assert res.ranked and all("55_and_older" in s.ages for s in res.ranked)
    assert any("age_focus" in e["reason"] for e in res.excluded)


def test_gender_focus_keeps_gender_neutral_segments(make_intake, store):
    _, _, res = run(make_intake, store, price=150_000, gender_focus="female", max_personas=10)
    assert res.ranked  # none of the shipped segments is gender specific, so nothing is dropped


def test_ranking_is_deterministic_and_sorted(make_intake, store):
    a = ids(run(make_intake, store, price=150_000, max_personas=10)[2])
    b = ids(run(make_intake, store, price=150_000, max_personas=10)[2])
    assert a == b
    sc = [s.score for s in run(make_intake, store, price=150_000, max_personas=10)[2].ranked]
    assert sc == sorted(sc, reverse=True)


# ---- incomplete data --------------------------------------------------------------------------------------
def test_without_income_bands_all_segments_use_the_same_components(make_intake):
    s = ReferenceStore(cache_path=None, snapshot_path=None)
    s.put_many([RefRecord("NGA", GNI_PC_LCU, 2024, 1_800_000.0, "t", "2026-01-01T00:00:00+00:00")])
    _, a, res = run(make_intake, s, price=150_000, max_personas=10)
    assert a.quintile_data == "none"
    assert all("affordability" not in x.components for x in res.ranked)
    assert {x.confidence for x in res.ranked} == {"low"}
    assert res.ranked_by.startswith(("features only", "rules only")) and res.notes


def test_partial_income_bands_do_not_skew_the_ranking(make_intake):
    s = ReferenceStore(cache_path=None, snapshot_path=None)
    from discover.personas.refdata.records import QUINTILE_SHARES
    s.put_many([RefRecord("NGA", GNI_PC_LCU, 2024, 1_800_000.0, "t", "2026-01-01T00:00:00+00:00"),
                RefRecord("NGA", QUINTILE_SHARES[1], 2022, 7.5, "t", "2026-01-01T00:00:00+00:00")])
    _, a, res = run(make_intake, s, price=40_000, max_personas=10)
    assert a.quintile_data == "partial"
    assert all("affordability" not in x.components for x in res.ranked)


def test_rules_only_when_nothing_separates_segments(make_intake):
    s = ReferenceStore(cache_path=None, snapshot_path=None)
    s.put_many([RefRecord("NGA", GNI_PC_LCU, 2024, 1_800_000.0, "t", "2026-01-01T00:00:00+00:00")])
    _, _, res = run(make_intake, s, price=40_000, description="Quite a nice thing to own and use.", max_personas=10)
    assert res.ranked_by.startswith("rules only")
    assert {x.score for x in res.ranked} == {0.5}


def test_result_is_json_serialisable(make_intake, store):
    import json
    json.dumps(run(make_intake, store, price=150_000)[2].to_dict())
