import pytest
from discover.personas.affordability import (PROFILES, ReferenceDataMissing, assess, market_position, reach_for, tier_for)
from discover.personas.refdata.records import FX_PER_USD, RefRecord
from discover.personas.refdata.store import ReferenceStore


@pytest.mark.parametrize("ratio,tier", [(0.0, "budget"), (0.0299, "budget"), (0.03, "mass"), (0.1499, "mass"),
                                         (0.15, "upper"), (0.3999, "upper"), (0.4, "premium"), (5.0, "premium")])
def test_tier_for_personal_durable_boundaries(ratio, tier):
    assert tier_for(ratio, PROFILES["personal_durable"].boundaries) == tier


@pytest.mark.parametrize("ratio,reach", [(0.1, "comfortable"), (0.15, "comfortable"), (0.2, "stretch"), (0.4, "stretch"), (0.41, "out_of_reach")])
def test_reach_for(ratio, reach):
    assert reach_for(ratio, PROFILES["personal_durable"].boundaries) == reach


def test_boundaries_are_increasing_for_every_profile():
    for p in PROFILES.values():
        b1, b2, b3 = p.boundaries
        assert 0 < b1 < b2 < b3


@pytest.mark.parametrize("price,tier", [(40_000, "budget"), (150_000, "mass"), (600_000, "upper"), (1_500_000, "premium")])
def test_tiers_for_a_phone_in_nigeria(make_intake, store, price, tier):
    a = assess(make_intake(price=price), store)
    assert a.tier == tier and a.country == "NGA" and a.local_currency == "NGN"
    assert a.ratio == pytest.approx(price / 1_800_000)


def test_quintile_income_and_reach_math(make_intake, store):
    a = assess(make_intake(price=600_000), store)
    assert a.quintile_data == "complete"
    q = {x.quintile: x for x in a.quintiles}
    assert q[1].annual_income_lcu == pytest.approx(0.075 * 5 * 1_800_000)
    assert q[5].annual_income_lcu == pytest.approx(0.455 * 5 * 1_800_000)
    assert [q[i].reach for i in range(1, 6)] == ["out_of_reach", "out_of_reach", "out_of_reach", "stretch", "comfortable"]
    assert a.reach_of(5) == "comfortable" and a.reach_of(9) == "unknown"


def test_cheap_product_is_comfortable_for_every_band(make_intake, store):
    a = assess(make_intake(price=40_000), store)
    assert {x.reach for x in a.quintiles} == {"comfortable"}


def test_price_in_other_currency_is_converted_and_labelled(make_intake, store):
    a = assess(make_intake(price=100, currency="USD"), store)
    assert a.local_price == pytest.approx(150_000) and a.tier == "mass"
    assert a.conversion["from"] == "USD" and a.conversion["to"] == "NGN"
    assert any("converted" in c for c in a.caveats)
    assert {i["indicator"] for i in a.inputs} >= {FX_PER_USD}


def test_local_price_needs_no_fx_even_if_rates_missing(make_intake):
    s = ReferenceStore(cache_path=None, snapshot_path=None)
    from discover.personas.refdata.records import GNI_PC_LCU
    s.put_many([RefRecord("NGA", GNI_PC_LCU, 2024, 1_800_000.0, "t", "2026-01-01T00:00:00+00:00")])
    a = assess(make_intake(price=40_000), s)
    assert a.conversion is None and a.quintile_data == "none"


def test_missing_fx_raises_with_guidance(make_intake, store):
    with pytest.raises(ReferenceDataMissing, match="XXX"):
        assess(make_intake(currency="XXX"), store)


def test_missing_gni_raises(make_intake):
    s = ReferenceStore(cache_path=None, snapshot_path=None)
    with pytest.raises(ReferenceDataMissing, match="refresh"):
        assess(make_intake(), s)


def test_stale_fx_adds_caveat(make_intake, store):
    store.put_many([RefRecord("USD", FX_PER_USD, None, 1.0, "t", "2000-01-01T00:00:00+00:00"),
                    RefRecord("NGN", FX_PER_USD, None, 1500.0, "t", "2000-01-01T00:00:00+00:00")])
    a = assess(make_intake(price=100, currency="USD"), store)
    assert any("older than" in c for c in a.caveats)


def test_subscription_is_annualised(make_intake, store):
    a = assess(make_intake(category="digital_subscription", price=2000, purchase_type="monthly"), store)
    assert a.local_annual_cost == 24_000 and a.profile == "subscription"
    assert a.ratio == pytest.approx(24_000 / 1_800_000)


def test_repeat_purchase_is_annualised(make_intake, store):
    a = assess(make_intake(category="food_beverage", price=500, purchase_type="repeat", purchases_per_year=100), store)
    assert a.local_annual_cost == 50_000 and a.profile == "everyday"


def test_free_product_never_hits_an_affordability_barrier(make_intake, store):
    a = assess(make_intake(category="fintech_app", price=0), store)
    assert a.tier == "budget" and {x.reach for x in a.quintiles} == {"comfortable"}
    assert any("free product" in c for c in a.caveats)


def test_market_position():
    assert market_position(100, []) is None
    assert market_position(70, [100, 100, 100])["position"] == "below"
    assert market_position(100, [100, 90, 110])["position"] == "in_line"
    m = market_position(200, [100, 100])
    assert m["position"] == "above" and m["competitor_median"] == 100 and m["n"] == 2


def test_market_position_flows_into_assessment(make_intake, store):
    a = assess(make_intake(price=40_000, competitor_prices=[80_000, 90_000, 100_000]), store)
    assert a.market_position["position"] == "below"


def test_other_countries_use_their_own_currency_and_income(make_intake, store):
    jp = assess(make_intake(location="Tokyo", currency="JPY", price=100_000), store)
    us = assess(make_intake(location="New York", currency="USD", price=800), store)
    assert jp.local_currency == "JPY" and us.local_currency == "USD"
    assert jp.ratio == pytest.approx(100_000 / 5_700_000) and us.ratio == pytest.approx(800 / 90_000)


def test_same_ratio_gives_same_tier_across_countries(make_intake, store):
    ng = assess(make_intake(price=180_000), store)           # 10% of 1.8M
    us = assess(make_intake(location="New York", currency="USD", price=9_000), store)  # 10% of 90k
    assert ng.tier == us.tier == "mass"


def test_caveats_always_state_national_average_limit(make_intake, store):
    a = assess(make_intake(), store)
    assert any("national average" in c for c in a.caveats)


def test_odd_share_sum_is_flagged(make_intake, store):
    from discover.personas.refdata.records import QUINTILE_SHARES
    store.put_many([RefRecord("NGA", QUINTILE_SHARES[5], 2021, 10.0, "t", "2026-01-01T00:00:00+00:00")])
    a = assess(make_intake(), store)
    assert any("sum to" in c for c in a.caveats)


def test_to_dict_is_json_serialisable(make_intake, store):
    import json
    json.dumps(assess(make_intake(price=100, currency="USD"), store).to_dict())
