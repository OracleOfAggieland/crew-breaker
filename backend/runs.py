"""Work Breaker starts and owns: a chat slot of its own, with a goal loop on it.

This is the one kind of work a cap holds on with no page open. The slot is
opened through ``ctx.chat_slots``, the supported handle Crew gives an app that
declares ``permissions.chatSlots``, so the turns run through Crew's own chat
runner, show in the sidebar under Breaker, and are stopped through the same
handle.

Stopping means the loop is removed, so no new cycle starts. A turn that is
already running is left to finish.
"""

from __future__ import annotations

import uuid
from typing import Any

DEFAULT_NUDGE = (
    "Keep working toward the goal above. If it is done, say so in one line and do nothing else."
)
STOP_REASON = "credit_cap"
MAX_PROMPT_CHARS = 20_000


class RunRefused(Exception):
    """The run could not be started, with a reason fit to show the owner."""


class Runs:
    """Starts and stops Breaker's own chat slots."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx
        self._sdk = getattr(ctx, "chat_slots", None)

    @property
    def available(self) -> bool:
        return self._sdk is not None

    async def start(
        self,
        state: Any,
        *,
        prompt: str,
        title: str,
        max_cycles: int,
        idle_secs: int,
        nudge: str = "",
    ) -> dict[str, Any]:
        """Open a slot, send the first prompt and arm the loop. Returns the run's record."""
        sdk = self._sdk
        if sdk is None:
            raise RunRefused("this Crew does not give apps chat slots, so Breaker can't own work here")
        key = f"{sdk.app_name}-{uuid.uuid4().hex[:10]}"
        try:
            slot, _created = await sdk.open(state, key)
            session = str(getattr(slot, "key", key) or key)
            sdk.set_title(state, slot, title)
            sdk.send(state, slot, prompt)
        except Exception as exc:  # noqa: BLE001 - reported to the owner, never raised into Crew
            raise RunRefused(f"Crew refused the new session: {type(exc).__name__}: {exc}") from exc
        record: dict[str, Any] = {
            "session": session,
            "title": title,
            "max_cycles": max_cycles,
            "idle_secs": idle_secs,
            "nudge": nudge or DEFAULT_NUDGE,
            "loop_id": "",
            "loop_note": "",
            "cycles_done": 0,
            "stopped": "",
        }
        if max_cycles > 0:
            loop_id, note = await self.arm(state, record, max_cycles)
            record["loop_id"], record["loop_note"] = loop_id, note
        return record

    async def arm(self, state: Any, record: dict[str, Any], cycles: int) -> tuple[str, str]:
        """Arm the goal loop on a run's slot: ``(loop id, note)``; no id means no loop."""
        sdk = self._sdk
        if sdk is None:
            return "", "this Crew does not give apps chat slots"
        try:
            slot = sdk.get(state, record["session"])
            if slot is None:
                slot = await sdk.restore(state, record["session"], adopt_closed=True)
            if slot is None:
                return "", "the session is gone"
            loop, error, _status = await sdk.arm_nudge(
                state,
                slot,
                message=str(record.get("nudge") or DEFAULT_NUDGE),
                idle_secs=int(record.get("idle_secs") or 60),
                max_cycles=int(cycles),
                caller="owner",
            )
        except Exception as exc:  # noqa: BLE001
            return "", f"{type(exc).__name__}: {exc}"
        if error is not None or loop is None:
            return "", str(error or "Crew armed no loop")
        return str(getattr(loop, "id", "") or ""), ""

    def loop(self, session: str) -> Any | None:
        """The live goal loop on one of Breaker's slots, or None."""
        sdk = self._sdk
        if sdk is None:
            return None
        try:
            nudges = sdk.nudges()
            return nudges.get_by_slot(session) if nudges is not None else None
        except Exception:  # noqa: BLE001 - "can't tell" reads as "no loop"
            return None

    async def stop_loop(self, session: str) -> tuple[bool, str]:
        """Remove the goal loop on one of Breaker's slots: ``(stopped, note)``.

        ``stopped`` is True when no loop is left on the slot, whether this call
        removed it or it had already ended.
        """
        sdk = self._sdk
        if sdk is None:
            return False, "this Crew does not give apps chat slots"
        try:
            nudges = sdk.nudges()
            if nudges is None:
                return True, "AutoNudge is not running, so no loop can fire"
            loop = nudges.get_by_slot(session)
            if loop is None:
                return True, "no loop was left on the session"
            loop_id = str(getattr(loop, "id", "") or "")
            removed = await nudges.remove(loop_id, stop_reason=STOP_REASON)
            return (True, "loop removed") if removed else (False, "Crew refused to remove the loop")
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
