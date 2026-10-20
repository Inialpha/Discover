"""Persona identity for display: a proposed first name, an illustrative gender, an age label and an avatar key.

All of this is presentation, not evidence: the persona is an illustration of a segment, not a real person. The segment's own
gender (if the rules set one) wins; otherwise the LLM may propose one; otherwise it alternates by rank so a set of personas
does not look uniform. `gender_basis` records which of these happened.
"""

from __future__ import annotations

import re
import zlib
from typing import Any

FEMALE = ("Ada", "Maya", "Lina", "Sara", "Nia", "Amina", "Zoe", "Mira", "Tolu", "Eva", "Rhea", "Chloe")
MALE = ("Tunde", "Omar", "Leo", "Kofi", "Ravi", "Sam", "Idris", "Noah", "Femi", "Ben", "Kai", "Yusuf")
NEUTRAL = ("Alex", "Sasha", "Jordan", "Robin")
_NAME = re.compile(r"^[A-Za-z][A-Za-z'’\-]{1,15}$")
AGE_CODE = {"24_and_younger": 22, "25_to_29": 27, "30_to_34": 32, "35_to_44": 40, "45_to_54": 50, "55_and_older": 62}
AGE_LABEL = {"24_and_younger": "under 25", "25_to_29": "25–29", "30_to_34": "30–34", "35_to_44": "35–44", "45_to_54": "45–54",
             "55_and_older": "55+"}
PALETTES = 6


def age_label(ages: list[str]) -> str:
    if not ages:
        return ""
    if len(ages) == 1:
        return AGE_LABEL.get(ages[0], ages[0])
    lo, hi = AGE_LABEL.get(ages[0], ages[0]), AGE_LABEL.get(ages[-1], ages[-1])
    if lo.startswith("under"):
        return f"{lo} to {hi}"
    return f"{lo.split('–')[0].rstrip('+')}–{hi.split('–')[-1]}" if "+" not in hi else f"{lo.split('–')[0]}+"


def clean_first_name(raw: Any) -> str | None:
    s = str(raw or "").strip().split(" ")[0]
    return s if _NAME.match(s) else None


def pick(seg_id: str, rank: int, gender: str) -> str:
    pool = {"female": FEMALE, "male": MALE}.get(gender, NEUTRAL)
    return pool[(zlib.crc32(seg_id.encode()) + rank) % len(pool)]


def avatar_key(gender: str, ages: list[str], seg_id: str) -> str:
    age = AGE_CODE.get(ages[len(ages) // 2], 35) if ages else 35
    return f"{gender[0]}-{age}-{zlib.crc32(seg_id.encode()) % PALETTES}"


def enrich(persona: dict[str, Any], seg_id: str, seg_gender: str | None, ages: list[str], rank: int) -> dict[str, Any]:
    """Adds display_name, gender, gender_basis, age_label, avatar, title, summary. `first_name`/`gender` from the LLM are optional."""
    llm_gender = str(persona.pop("gender", "") or "").lower()
    llm_gender = llm_gender if llm_gender in ("male", "female") else ""
    if seg_gender in ("male", "female"):
        gender, basis = seg_gender, "segment"
    elif llm_gender:
        gender, basis = llm_gender, "illustrative"
    else:
        gender, basis = ("female" if rank % 2 else "male"), "illustrative"
    first = clean_first_name(persona.pop("first_name", None))
    persona["display_name"] = first or pick(seg_id, rank, gender)
    persona["name_basis"] = "llm" if first else "generated"
    persona["gender"], persona["gender_basis"] = gender, basis
    persona["age_label"] = age_label(ages)
    persona["avatar"] = avatar_key(gender, ages, seg_id)
    persona["title"] = persona.get("name", "")
    persona["summary"] = persona.get("headline", "")
    return persona
