from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ...engine.personas import avatar
from ...engine.personas.geography import MARKETS
from ...engine.personas.intake import CATEGORIES, PURCHASE_TYPES
from ...engine.personas.segments import AGES

router = APIRouter(tags=["meta"])

LABELS = {"smartphone": "Smartphone", "computing": "Computers & tablets", "apparel_footwear": "Clothing & footwear",
          "education_service": "Education service", "other": "Other physical product", "beauty_personal_care": "Beauty & personal care",
          "food_beverage": "Food & drink", "health_wellness": "Health & wellness", "digital_subscription": "Digital subscription",
          "fintech_app": "Fintech app", "software_saas": "Software / SaaS", "home_appliance": "Home appliance", "vehicle": "Vehicle",
          "travel_hospitality": "Travel & hospitality", "entertainment_media": "Entertainment & media"}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/meta")
def meta() -> dict:
    return {
        "categories": [{"id": c, "label": LABELS.get(c, c), "profile": p} for c, p in CATEGORIES.items()],
        "purchase_types": [{"id": "one_off", "label": "One-off purchase"}, {"id": "monthly", "label": "Monthly subscription"},
                           {"id": "annual", "label": "Annual subscription"}, {"id": "repeat", "label": "Bought repeatedly (set times a year)"}],
        "markets": [{"iso2": m.iso2, "name": m.name, "currency": m.currency} for m in MARKETS.values()],
        "age_buckets": list(AGES),
        "limits": {"max_personas": 10, "max_competitors": 10, "max_features": 12},
    }


@router.get("/api/avatars/{key}.svg")
def avatar_svg(key: str) -> Response:
    if len(key) > 20:
        raise HTTPException(404)
    return Response(avatar.svg(key), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})
