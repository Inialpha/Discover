"""Turns a stored Analysis into what clients and exports show: persona edits applied, nothing else changed."""

from __future__ import annotations

import copy
import re
from typing import Any

from ..models import Analysis

EDITABLE = ("display_name", "title", "summary")


def merged_result(a: Analysis) -> dict[str, Any] | None:
    if not a.result:
        return None
    res = user_facing(copy.deepcopy(a.result))
    for key, edit in (a.edits or {}).items():
        try:
            p = res["personas"][int(key)]
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        for f in EDITABLE:
            if edit.get(f):
                p[f] = edit[f]
                p.setdefault("edited_fields", [])
                if f not in p["edited_fields"]:
                    p["edited_fields"].append(f)
    return res


# Users should see what is confirmed by data, what is a suggestion and what is not confirmed, not which tool produced it.
_PLAIN = [
    (r"Template persona: no LLM was used, so there are no messages, platforms or motivations\.",
     "This persona was built from data and rules only, so it has no suggested messages or platforms."),
    (r"LLM failed[^.]*\.?", "The written suggestions could not be produced for this persona, so only data and rules are shown."),
    (r"Qloo's", "the data's"), (r"\bQloo\b", "the market data"), (r"\bLLMs?\b", "the writer"), (r"\blanguage model\b", "writer"),
    (r"\bthe the\b", "the"),
]


def plain(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    first_upper = text[:1].isupper()
    for pat, rep in _PLAIN:
        text = re.sub(pat, rep, text)
    return text[:1].upper() + text[1:] if first_upper else text


def _plain_market(m: dict[str, Any]) -> None:
    for e in m.get("ledger") or []:
        e["result"] = plain(e.get("result"))
    m["notes"] = [plain(n) for n in m.get("notes") or []]


def user_facing(res: dict[str, Any]) -> dict[str, Any]:
    """Rewrite engine wording in place for display and export."""
    res["evidence_notes"] = [plain(n) for n in res.get("evidence_notes") or []]
    sc = res.get("scoring") or {}
    sc["notes"] = [plain(n) for n in sc.get("notes") or []]
    for p in res.get("personas") or []:
        p["caveats"] = [plain(c) for c in p.get("caveats") or []]
    if res.get("market"):
        _plain_market(res["market"])
    return res
