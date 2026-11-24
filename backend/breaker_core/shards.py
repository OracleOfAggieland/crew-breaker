"""Reading Crew's usage log, one line at a time.

Crew appends one JSON object per turn to ``usage/tokens/YYYY-MM-DD.jsonl``
under its data home. The writes are best-effort, so the last line of a file
may be half written. This module only parses text; opening files is the
caller's job.
"""

from __future__ import annotations

import json
from typing import Any

from .ledger import TurnRow


def parse_line(shard: str, line_number: int, text: str) -> TurnRow | None:
    """One usage row, or None for anything that isn't a whole one."""
    text = text.strip()
    if not text:
        return None
    try:
        data: Any = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("_type", "tokens") != "tokens":
        return None
    slot = data.get("slot")
    if not isinstance(slot, str) or not slot:
        return None
    return TurnRow(
        shard=shard,
        line=line_number,
        slot=slot,
        credits=data.get("credits", 0.0),
        dollars=data.get("cost", 0.0),
        surface=_text(data.get("surface")),
        app=_text(data.get("app")),
        ts=_text(data.get("ts")),
    )


def split_complete(buffer: str) -> tuple[list[str], str]:
    """Split text into whole lines and the unfinished tail.

    A line counts only once its newline has been written, so a row caught
    mid-write is left for the next read.
    """
    if not buffer:
        return [], ""
    parts = buffer.split("\n")
    return parts[:-1], parts[-1]


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""
