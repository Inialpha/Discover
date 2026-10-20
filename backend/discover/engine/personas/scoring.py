"""Rank candidate segments with a transparent score.

score = weighted mean of the components that have data, weights renormalised over the available ones:
  affordability (0.35) mean reach over the segment's income bands: comfortable=1, stretch=0.5, out_of_reach=0
  feature_fit   (0.25) share of the segment's keyword cues found in the product's features/description (2 hits = full)
  qloo_fit      (0.40) optional, from Qloo: how strongly the competitor/anchor audience skews to this segment's age
                       bands (relative index mapped to 0..1; see personas/evidence.py)
The score is an ordering aid, NOT a probability of purchase and NOT a share of buyers. Every component and its
inputs are returned so a report can show exactly why a segment ranked where it did.
Confidence is capped at "medium": "medium" needs real income-band data plus at least one more component.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .affordability import Affordability
from .intake import ProductIntake
from .segments import SEGMENTS, Segment

WEIGHTS = {"affordability": 0.35, "feature_fit": 0.25, "qloo_fit": 0.40}
REACH_VALUE = {"comfortable": 1.0, "stretch": 0.5, "out_of_reach": 0.0}
RULES_ONLY_SCORE = 0.5


@dataclass
class SegmentScore:
    id: str
    label: str
    description: str
    ages: tuple[str, ...]
    gender: str | None
    score: float
    confidence: str
    components: dict[str, dict[str, Any]]
    reach: dict[int, str]
    matched_keywords: list[str]
    rationale: list[str]
    basis: str = "rule"
    niche: bool = False   # price out of reach for every band the segment draws on
    tied: bool = False    # same score as another segment and no feature/Qloo evidence to separate them

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["ages"] = list(self.ages)
        d["reach"] = {str(k): v for k, v in self.reach.items()}
        return d


@dataclass
class ScoringResult:
    ranked: list[SegmentScore]
    excluded: list[dict[str, str]]
    omitted_by_limit: int
    ranked_by: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ranked": [s.to_dict() for s in self.ranked], "excluded": self.excluded,
                "omitted_by_limit": self.omitted_by_limit, "ranked_by": self.ranked_by, "notes": self.notes}


def _text(intake: ProductIntake) -> str:
    return " ".join([intake.name, intake.description, *intake.features]).lower()


def keyword_hits(seg: Segment, text: str) -> list[str]:
    hits = []
    for k in seg.keywords:
        pat = r"(?<![a-z0-9])" + re.escape(k.lower()) + r"(?![a-z0-9])"
        if re.search(pat, text):
            hits.append(k)
    return hits


def affordability_component(seg: Segment, aff: Affordability) -> tuple[float | None, dict[int, str]]:
    reach = {q: aff.reach_of(q) for q in seg.quintiles}
    known = [REACH_VALUE[r] for r in reach.values() if r in REACH_VALUE]
    if not known:
        return None, reach
    return sum(known) / len(known), reach


def qloo_scores_from_values(affinities: dict[str, list[float]]) -> dict[str, float]:
    """segment id -> mean of 0..1 values. Segments with no values are left out (no data, not zero)."""
    out: dict[str, float] = {}
    for sid, vals in affinities.items():
        v = [x for x in vals if isinstance(x, (int, float))]
        if v:
            out[sid] = max(0.0, min(1.0, sum(v) / len(v)))
    return out


def score_segments(intake: ProductIntake, aff: Affordability, qloo_fit: dict[str, float] | None = None) -> ScoringResult:
    text = _text(intake)
    use_income = aff.quintile_data == "complete" or aff.local_annual_cost == 0
    excluded: list[dict[str, str]] = []
    scored: list[SegmentScore] = []
    for seg in SEGMENTS:
        if intake.category not in seg.categories:
            continue  # not a rule match for this product type; not worth listing
        if aff.tier not in seg.tiers:
            excluded.append({"id": seg.id, "label": seg.label,
                             "reason": f"rule: this segment is not listed for the '{aff.tier}' affordability tier"})
            continue
        if intake.gender_focus and seg.gender and seg.gender != intake.gender_focus:
            excluded.append({"id": seg.id, "label": seg.label, "reason": f"filter: gender_focus={intake.gender_focus}"})
            continue
        if intake.age_focus and not set(intake.age_focus) & set(seg.ages):
            excluded.append({"id": seg.id, "label": seg.label, "reason": f"filter: age_focus={','.join(intake.age_focus)}"})
            continue
        a_val, reach = affordability_component(seg, aff)
        if not use_income:
            a_val = None  # one comparable component set for every segment; partial band data is not enough
        niche = bool(use_income and aff.local_annual_cost > 0 and reach and all(r == "out_of_reach" for r in reach.values()))
        hits = keyword_hits(seg, text)
        comps: dict[str, dict[str, Any]] = {}
        if a_val is not None:
            comps["affordability"] = {"value": round(a_val, 3), "weight": WEIGHTS["affordability"],
                                      "detail": {f"band_{q}": r for q, r in reach.items()}}
        comps["feature_fit"] = {"value": round(min(1.0, len(hits) / 2), 3), "weight": WEIGHTS["feature_fit"],
                                "detail": {"matched": hits, "of": len(seg.keywords)}}
        if qloo_fit and seg.id in qloo_fit:
            comps["qloo_fit"] = {"value": round(qloo_fit[seg.id], 3), "weight": WEIGHTS["qloo_fit"],
                                 "detail": "competitor/anchor audience skew toward this segment's age bands (relative index)"}
        total_w = sum(c["weight"] for c in comps.values())
        score = sum(c["value"] * c["weight"] for c in comps.values()) / total_w
        has_income = "affordability" in comps
        conf = "medium" if has_income and len(comps) >= 2 else "low"
        rationale = [f"Rule: listed for {intake.category} products at the '{aff.tier}' tier "
                     f"(yearly cost is {aff.ratio:.1%} of average annual income)."]
        if has_income:
            rationale.append("Income bands " + ", ".join(f"{q}={r}" for q, r in reach.items()) + ".")
        else:
            rationale.append("Income-band check skipped: the country's income distribution is incomplete in the reference data.")
        if niche:
            rationale.append("Niche: the price is out of reach for every income band this segment draws on, so only the "
                             "top slice of the highest band could buy at this price.")
        if hits:
            rationale.append("Product text mentions: " + ", ".join(hits) + ".")
        scored.append(SegmentScore(seg.id, seg.label, seg.description, seg.ages, seg.gender, round(score, 4), conf,
                                   comps, reach, hits, rationale, niche=niche))

    notes: list[str] = []
    ranked_by = "affordability + features" + (" + Qloo audience fit" if qloo_fit else "")
    if scored and not any("affordability" in s.components for s in scored):
        ranked_by = "features only"
        notes.append("Income-band data is incomplete for this country, so ranking uses feature cues only; the tier rule still "
                     "applies. Run `discover refdata refresh` to fetch the full income distribution; treat the order as weak.")
    if scored and all(s.components["feature_fit"]["value"] == 0 for s in scored) and not any(
            "affordability" in s.components or "qloo_fit" in s.components for s in scored):
        for s in scored:
            s.score = RULES_ONLY_SCORE
        ranked_by = "rules only (no data to separate segments)"
        notes.append("Nothing in the product text or income data separates the segments; they are listed by rule only.")
    scored.sort(key=lambda s: (-s.score, s.label))
    by_score: dict[float, list[SegmentScore]] = {}
    for sc in scored:
        by_score.setdefault(sc.score, []).append(sc)
    for group in by_score.values():
        if len(group) > 1 and all(g.components["feature_fit"]["value"] == 0 and "qloo_fit" not in g.components for g in group):
            for g in group:
                g.tied = True
                g.rationale.append("No feature or Qloo evidence separates this segment from others with the same score.")
    if any(s.niche for s in scored):
        notes.append("At this price some segments are niche: no income band can afford it comfortably.")
    cap = max(1, int(intake.max_personas))
    return ScoringResult(ranked=scored[:cap], excluded=excluded, omitted_by_limit=max(0, len(scored) - cap),
                         ranked_by=ranked_by, notes=notes)
