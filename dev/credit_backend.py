"""A stand-in for kiro-cli that reports credits, so Breaker can be tested for nothing.

Kiro Crew ships a fake model backend for its own tests
(``kiro_crew.testing.fake_acp_backend``). It answers every prompt and bills
nothing. This file runs that backend and adds one thing: before each prompt's
result it sends the frame kiro-cli sends to report what the turn cost
(``_kiro.dev/metadata`` with a ``meteringUsage`` entry in credits). Crew then
writes a usage row with real-looking credits, and Breaker meters it.

Point a development gateway at it and no account, sign-in or credit is used:

    KIROCREW_KIRO_BIN=<a script that runs: python dev/credit_backend.py %*>

Each turn bills ``BREAKER_FAKE_CREDITS`` credits (default 12). A prompt that
contains ``credits=40`` bills 40 instead.

A development tool only. It imports ``kiro_crew``, which the app itself never
does, and it must run under the Python that has Kiro Crew installed.
"""

from __future__ import annotations

import os
import re
from typing import Any

from kiro_crew.testing import fake_acp_backend as fake

DEFAULT_CREDITS = float(os.environ.get("BREAKER_FAKE_CREDITS", "12") or 12)
ASKED = re.compile(r"credits=(\d+(?:\.\d+)?)")

_prompt: dict[str, Any] = {"request": None, "session": "", "credits": DEFAULT_CREDITS}
_handle = fake._handle
_result = fake._result


def handle(message: dict[str, Any]) -> None:
    """Note which prompt is being answered, then let the fake backend answer it."""
    if message.get("method") == "session/prompt":
        params = message.get("params") or {}
        asked = ASKED.findall(fake._prompt_text(params))
        _prompt.update(
            request=message.get("id"),
            session=str(params.get("sessionId") or ""),
            credits=float(asked[-1]) if asked else DEFAULT_CREDITS,
        )
    _handle(message)


def result(request_id: Any, payload: dict[str, Any]) -> None:
    """Bill the turn just before its result goes out, as kiro-cli does."""
    if request_id == _prompt["request"] and isinstance(payload, dict) and "stopReason" in payload:
        fake._notify(
            "_kiro.dev/metadata",
            {
                "sessionId": _prompt["session"],
                "meteringUsage": [{"unit": "credit", "value": _prompt["credits"]}],
            },
        )
        _prompt["request"] = None
    _result(request_id, payload)


fake._handle = handle
fake._result = result

if __name__ == "__main__":
    fake.main()
