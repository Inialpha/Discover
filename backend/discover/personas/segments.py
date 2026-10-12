"""Rule table: which kinds of buyers could plausibly want a product of a given category and affordability tier.

These are documented *assumptions* (basis = "rule"), not measured facts. Each segment says:
  - who it is (Qloo age buckets, optional gender),
  - which income quintiles it typically draws on (1 = lowest 20%, 5 = highest 20%),
  - which categories and affordability tiers it applies to,
  - feature keywords that make it a better fit when the product's features mention them.
No tier is privileged: budget and mass-market products have their own segments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AGES = ("24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older")
ALL_TIERS = ("budget", "mass", "upper", "premium")
DEVICES = ("smartphone", "computing")
DIGITAL = ("digital_subscription", "fintech_app")
ALL_CATEGORIES = ("smartphone", "computing", "apparel_footwear", "education_service", "other", "beauty_personal_care",
                  "food_beverage", "health_wellness", "digital_subscription", "fintech_app", "home_appliance", "vehicle",
                  "travel_hospitality", "entertainment_media")


@dataclass(frozen=True)
class Segment:
    id: str
    label: str
    description: str
    ages: tuple[str, ...]
    quintiles: tuple[int, ...]
    categories: tuple[str, ...]
    tiers: tuple[str, ...]
    keywords: tuple[str, ...] = ()
    gender: str | None = None
    basis: str = "rule"


SEGMENTS: tuple[Segment, ...] = (
    Segment("students_budget", "Budget-conscious students", "Students paying for themselves or on tight allowances.",
            ("24_and_younger",), (1, 2, 3), (*DEVICES, "apparel_footwear", *DIGITAL, "beauty_personal_care", "food_beverage",
                                            "entertainment_media", "education_service"), ("budget", "mass"),
            ("student", "cheap", "affordable", "battery", "storage", "study", "campus", "data")),
    Segment("students_supported", "Family-supported students", "Students whose purchases are funded by family.",
            ("24_and_younger",), (3, 4, 5), (*DEVICES, "apparel_footwear", "education_service", "entertainment_media",
                                            "beauty_personal_care", "travel_hospitality"), ("mass", "upper", "premium"),
            ("student", "camera", "style", "gaming", "design", "social")),
    Segment("first_time_users", "First-time or entry-level users", "People buying their first device or service, price is the main filter.",
            ("24_and_younger", "25_to_29", "30_to_34"), (1, 2), ("smartphone", *DIGITAL, "food_beverage", "beauty_personal_care"),
            ("budget",), ("simple", "easy", "affordable", "durable", "dual sim", "battery")),
    Segment("early_career", "Early-career professionals", "Employed, building income, buying useful upgrades.",
            ("25_to_29", "30_to_34"), (2, 3, 4), ALL_CATEGORIES, ("mass", "upper"),
            ("work", "productivity", "commute", "career", "battery", "professional")),
    Segment("high_earners_young", "Higher-earning young professionals", "Disposable income, willing to pay for quality or status.",
            ("25_to_29", "30_to_34"), (4, 5), ALL_CATEGORIES, ("upper", "premium"),
            ("premium", "design", "camera", "performance", "luxury", "status")),
    Segment("established_adults", "Established adults", "Stable income, mid-career, buys for reliability and value.",
            ("35_to_44",), (3, 4, 5), ALL_CATEGORIES, ("mass", "upper", "premium"),
            ("reliable", "quality", "warranty", "family", "work")),
    Segment("parents_families", "Parents and young families", "Households with children, buying for the home and family.",
            ("30_to_34", "35_to_44"), (2, 3, 4), ("home_appliance", "food_beverage", "education_service", "health_wellness",
                                                  "vehicle", "travel_hospitality", "beauty_personal_care", "smartphone"),
            ("budget", "mass", "upper"), ("family", "kids", "safe", "home", "child", "household")),
    Segment("cost_conscious_households", "Cost-conscious households", "Households watching spending; value and durability matter.",
            ("30_to_34", "35_to_44", "45_to_54"), (1, 2, 3), ("food_beverage", "home_appliance", "health_wellness",
                                                              "beauty_personal_care", "smartphone"), ("budget", "mass"),
            ("value", "durable", "save", "energy", "bulk", "affordable")),
    Segment("small_business_owners", "Small-business owners and self-employed", "Buy tools that earn money; price vs return matters.",
            ("30_to_34", "35_to_44", "45_to_54"), (2, 3, 4), (*DEVICES, *DIGITAL, "vehicle", "home_appliance"),
            ("budget", "mass", "upper"), ("business", "payments", "invoice", "inventory", "customers", "productivity")),
    Segment("mature_affluent", "Mature, higher-income adults", "Established wealth, buys comfort, health and experiences.",
            ("45_to_54", "55_and_older"), (4, 5), ("vehicle", "travel_hospitality", "health_wellness", "home_appliance",
                                                   "smartphone", "computing", "entertainment_media"), ("upper", "premium"),
            ("comfort", "luxury", "health", "quality", "premium")),
    Segment("older_value_seekers", "Older adults on moderate or fixed income", "Prefer simple, reliable products at fair prices.",
            ("55_and_older",), (1, 2, 3), ("smartphone", "health_wellness", "home_appliance", "food_beverage", *DIGITAL),
            ("budget", "mass"), ("simple", "easy", "large", "health", "reliable", "support")),
    Segment("tech_enthusiasts", "Technology enthusiasts", "Follow specs and launches closely; pay for performance.",
            ("24_and_younger", "25_to_29", "30_to_34"), (3, 4, 5), (*DEVICES, "digital_subscription", "entertainment_media"),
            ("mass", "upper", "premium"), ("camera", "processor", "5g", "ai", "display", "performance", "spec", "chip")),
    Segment("gamers", "Gamers", "Regular players; care about performance, battery and cost of play.",
            ("24_and_younger", "25_to_29", "30_to_34"), (2, 3, 4, 5), (*DEVICES, "entertainment_media", "digital_subscription"),
            ("budget", "mass", "upper", "premium"), ("gaming", "game", "fps", "refresh", "graphics", "performance")),
    Segment("creators", "Content creators and freelancers", "Make content or client work on their device.",
            ("24_and_younger", "25_to_29", "30_to_34"), (2, 3, 4), (*DEVICES, "digital_subscription", "fintech_app", "apparel_footwear"),
            ("budget", "mass", "upper"), ("camera", "video", "editing", "content", "creator", "storage", "audio")),
    Segment("remote_workers", "Remote and hybrid workers", "Work from home or on the move.",
            ("25_to_29", "30_to_34", "35_to_44"), (3, 4, 5), ("computing", "digital_subscription", "home_appliance", "fintech_app"),
            ("mass", "upper", "premium"), ("remote", "productivity", "battery", "wifi", "ergonomic", "meeting")),
    Segment("fitness_focused", "Fitness and wellness focused", "Active people spending on health and training.",
            ("24_and_younger", "25_to_29", "30_to_34", "35_to_44"), (2, 3, 4, 5), ("health_wellness", "apparel_footwear",
                                                                                  "food_beverage", "digital_subscription"),
            ("budget", "mass", "upper", "premium"), ("fitness", "workout", "protein", "run", "sport", "wellness", "tracking")),
    Segment("style_conscious", "Style and beauty conscious", "Buy for appearance and trend.",
            ("24_and_younger", "25_to_29", "30_to_34"), (2, 3, 4, 5), ("beauty_personal_care", "apparel_footwear", "smartphone"),
            ("budget", "mass", "upper", "premium"), ("style", "beauty", "skin", "trend", "fashion", "look", "camera")),
    Segment("leisure_travelers", "Leisure travellers and experience seekers", "Spend on trips, events and entertainment.",
            ("25_to_29", "30_to_34", "35_to_44", "45_to_54"), (3, 4, 5), ("travel_hospitality", "entertainment_media",
                                                                           "apparel_footwear", "smartphone"),
            ("mass", "upper", "premium"), ("travel", "holiday", "event", "experience", "weekend", "tour")),
    Segment("everyday_buyers", "Everyday mass-market buyers", "Broad adult base buying routine items at affordable prices.",
            ("25_to_29", "30_to_34", "35_to_44", "45_to_54"), (1, 2, 3, 4), ("food_beverage", "beauty_personal_care",
                                                                             "health_wellness", "apparel_footwear", "other"),
            ("budget", "mass"), ("everyday", "daily", "family", "affordable", "pack")),
)


def by_id(seg_id: str) -> Segment | None:
    return next((s for s in SEGMENTS if s.id == seg_id), None)


def candidates(category: str, tier: str) -> list[Segment]:
    """Segments whose rules cover this category and affordability tier."""
    return [s for s in SEGMENTS if category in s.categories and tier in s.tiers]
