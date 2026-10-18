"""Turns a stored Analysis into what clients and exports show: persona edits applied, nothing else changed."""

from __future__ import annotations

import copy
from typing import Any

from ..models import Analysis

EDITABLE = ("display_name", "title", "summary")


def merged_result(a: Analysis) -> dict[str, Any] | None:
    if not a.result:
        return None
    res = copy.deepcopy(a.result)
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
