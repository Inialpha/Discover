"""Persona-discovery step 1 (no Qloo, no LLM): intake -> affordability -> ranked candidate segments.

Output is a plain dict so the CLI, an API endpoint or the later Qloo/LLM steps can all use it.
"""

from __future__ import annotations

from typing import Any

from .affordability import assess
from .fx_note import FX_ATTRIBUTION
from .intake import ProductIntake
from .refdata.store import ReferenceStore
from .scoring import score_segments


class IntakeError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def analyse(intake: ProductIntake, store: ReferenceStore, qloo_fit: dict[str, float] | None = None) -> dict[str, Any]:
    errs = intake.validate()
    if errs:
        raise IntakeError(errs)
    aff = assess(intake, store)
    scoring = score_segments(intake, aff, qloo_fit)
    return {
        "intake": intake.to_dict(),
        "affordability": aff.to_dict(),
        "segments": scoring.to_dict(),
        "attribution": ["World Bank Open Data (CC BY 4.0)"] + ([FX_ATTRIBUTION] if aff.conversion else []),
        "labels": {"affordability": "calculated from cited statistics", "segments": "rule-based candidates (assumptions)",
                   "score": "ordering aid, not a probability or share of buyers"},
    }
