"""Writes every artifact of a run (requests, raw responses, evidence, report) to one folder."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (slug[:max_len].rstrip("-")) or "run"


class RunRecorder:
    """Owns a run directory. Paths passed around are always relative to it."""

    def __init__(self, run_dir: Path):
        self.dir = Path(run_dir)
        (self.dir / "qloo").mkdir(parents=True, exist_ok=True)
        (self.dir / "llm").mkdir(parents=True, exist_ok=True)
        self._seq = 0

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def write_json(self, rel: str, obj: Any) -> str:
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
        )
        return rel

    def write_text(self, rel: str, text: str) -> str:
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return rel

    def append_jsonl(self, rel: str, obj: Any) -> None:
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
