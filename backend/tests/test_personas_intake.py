import pytest
from discover.personas.geography import resolve_market
from discover.personas.intake import CATEGORIES, ProductIntake


def test_valid_intake_has_no_errors(make_intake):
    assert make_intake().validate() == []


@pytest.mark.parametrize("field,value,needle", [
    ("name", " ", "name"), ("description", "short", "description"), ("category", "spaceship", "category"),
    ("price", -1, "price"), ("currency", "naira", "currency"), ("purchase_type", "lease", "purchase_type"),
    ("location", "", "location"), ("max_personas", 0, "max_personas"), ("max_personas", 11, "max_personas"),
    ("gender_focus", "other", "gender_focus"), ("competitor_prices", [10, 0], "competitor_prices"),
])
def test_invalid_fields_are_reported(make_intake, field, value, needle):
    errs = make_intake(**{field: value}).validate()
    assert any(needle in e for e in errs), errs


def test_free_product_is_allowed(make_intake):
    assert make_intake(price=0).validate() == []


def test_repeat_needs_purchases_per_year(make_intake):
    assert any("purchases_per_year" in e for e in make_intake(purchase_type="repeat").validate())
    assert make_intake(purchase_type="repeat", purchases_per_year=12).validate() == []


def test_annual_cost(make_intake):
    assert make_intake(price=100).annual_cost == 100
    assert make_intake(price=100, purchase_type="monthly").annual_cost == 1200
    assert make_intake(price=100, purchase_type="annual").annual_cost == 100
    assert make_intake(price=5, purchase_type="repeat", purchases_per_year=52).annual_cost == 260


def test_unknown_city_requires_country(make_intake):
    errs = make_intake(location="Gotham").validate()
    assert any("country" in e for e in errs)
    assert make_intake(location="Gotham", country="NG").validate() == []


def test_unknown_explicit_country_is_an_error_not_overridden_by_city(make_intake):
    errs = make_intake(location="Lagos", country="Atlantis").validate()
    assert any("not one of the supported markets" in e for e in errs)


@pytest.mark.parametrize("loc,country,iso3", [
    ("Lagos", None, "NGA"), ("Uyo, Nigeria", None, "NGA"), ("new york", None, "USA"), ("Tokyo", None, "JPN"),
    ("somewhere", "UK", "GBR"), ("Nairobi", None, "KEN"), ("X", "ZAF", "ZAF"), ("X", "south africa", "ZAF"),
    ("Berlin, Germany", None, "DEU"), ("Dubai", None, "ARE"),
])
def test_resolve_market(loc, country, iso3):
    assert resolve_market(loc, country).iso3 == iso3


def test_resolve_market_never_guesses():
    assert resolve_market("Atlantis") is None
    assert resolve_market(None) is None


def test_every_category_maps_to_a_known_profile():
    from discover.personas.affordability import PROFILES
    assert set(CATEGORIES.values()) <= set(PROFILES)


def test_from_dict_roundtrip_and_normalisation():
    d = {"name": "X", "description": "does a useful thing well", "category": "fintech_app", "price": 0, "currency": "ngn",
         "location": "Lagos", "features": [" a ", "", "b"], "competitors": None, "unknown_field": 1}
    p = ProductIntake.from_dict(d)
    assert p.currency == "NGN" and p.features == ["a", "b"] and p.competitors == []
    out = p.to_dict()
    assert out["market"]["iso3"] == "NGA" and out["annual_cost"] == 0
