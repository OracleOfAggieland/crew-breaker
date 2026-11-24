"""Breaker: the ledger, the caps on it, and a record of what happened.

Still pure: no I/O and no clock. The caller feeds facts in and gets signals
back, and can save and restore the whole thing as plain JSON.
"""

from __future__ import annotations

from typing import Any

from .cap import ENFORCE, SHADOW, Cap, Signal
from .ledger import Ledger, Snapshot, TurnRow

HISTORY_LIMIT = 500


class Breaker:
    """One ledger and the caps set on its sessions."""

    def __init__(self) -> None:
        self.ledger = Ledger()
        self.caps: dict[str, Cap] = {}
        self.seq = 0
        self.history: list[dict[str, Any]] = []
        self.meter_ok = True
        self.meter_note = ""

    # ---- facts in ----------------------------------------------------------

    def feed_row(self, row: TurnRow) -> list[Signal]:
        """A settled usage row arrived."""
        self.seq += 1
        if not self.ledger.add_row(row):
            return []
        self.meter_ok, self.meter_note = True, ""
        return self._check_caps()

    def feed_snapshot(self, snapshot: Snapshot) -> list[Signal]:
        """A look at the subagents running right now."""
        self.seq += 1
        self.ledger.add_snapshot(snapshot)
        return self._check_caps()

    def meter_unreadable(self, note: str = "") -> list[Signal]:
        """The meter could not be read. Breaker fails open: nothing trips."""
        self.seq += 1
        self.meter_ok, self.meter_note = False, note
        return []

    # ---- owner's moves -----------------------------------------------------

    def set_cap(self, session: str, limit: Any, mode: str | None = None, warn_pct: Any = None) -> Cap:
        """Set or change a session's cap. Never clears a trip."""
        self.seq += 1
        cap = self.caps.get(session) or Cap(session=session)
        cap.set(limit, mode, warn_pct)
        self.caps[session] = cap
        self._note("cap_set", session, limit=cap.limit, mode=cap.mode)
        self._check_one(cap)
        return cap

    def remove_cap(self, session: str) -> None:
        """Take the cap off a session altogether."""
        self.seq += 1
        if self.caps.pop(session, None) is not None:
            self._note("cap_removed", session)

    def restart(self, session: str) -> list[Signal]:
        """The owner restarted the work. Over the limit, it trips again at once."""
        self.seq += 1
        cap = self.caps.get(session)
        if cap is None:
            return []
        cap.restart()
        self._note("restarted", session, limit=cap.limit)
        return self._check_one(cap)

    # ---- reading -----------------------------------------------------------

    def report(self) -> dict[str, Any]:
        """Everything a page needs to draw the state."""
        sessions = []
        for key in sorted(set(self.ledger.roots()) | set(self.caps)):
            total = self.ledger.total(key)
            cap = self.caps.get(key)
            sessions.append(
                {
                    "session": key,
                    "own": total.own,
                    "children": total.children,
                    "total": total.total,
                    "dollars": total.dollars,
                    "runs": total.runs,
                    "running": list(total.running),
                    "surface": self.ledger.surface.get(key, ""),
                    "app": self.ledger.app.get(key, ""),
                    "orphan_run": self.ledger.is_orphan_run(key),
                    "bills_in_dollars": total.dollars > 0 and total.total == 0,
                    "cap": cap.to_json() if cap else None,
                }
            )
        return {
            "seq": self.seq,
            "meter": {"ok": self.meter_ok, "note": self.meter_note},
            "sessions": sessions,
            "coverage": self.ledger.coverage(),
            "grand_total": self.ledger.grand_total(),
        }

    # ---- keeping -----------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "version": 1,
            "seq": self.seq,
            "ledger": self.ledger.to_json(),
            "caps": [cap.to_json() for cap in self.caps.values()],
            "history": list(self.history),
        }

    @classmethod
    def from_json(cls, data: Any) -> "Breaker":
        breaker = cls()
        if not isinstance(data, dict):
            return breaker
        breaker.ledger = Ledger.from_json(data.get("ledger"))
        seq = data.get("seq")
        breaker.seq = seq if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0 else 0
        caps = data.get("caps")
        if isinstance(caps, list):
            for item in caps:
                cap = Cap.from_json(item)
                if cap is not None:
                    breaker.caps[cap.session] = cap
        history = data.get("history")
        if isinstance(history, list):
            breaker.history = [h for h in history if isinstance(h, dict)][-HISTORY_LIMIT:]
        return breaker

    # ---- inside ------------------------------------------------------------

    def _check_caps(self) -> list[Signal]:
        signals: list[Signal] = []
        for cap in self.caps.values():
            signals.extend(self._check_one(cap))
        return signals

    def _check_one(self, cap: Cap) -> list[Signal]:
        total = self.ledger.total(cap.session)
        signals = cap.evaluate(total.total, total.running, self.seq)
        for signal in signals:
            self._note(
                signal.kind,
                signal.session,
                total=signal.total,
                limit=signal.limit,
                overshoot=signal.overshoot,
                running=list(signal.running),
                mode=cap.mode,
            )
        return signals

    def _note(self, kind: str, session: str, **details: Any) -> None:
        self.history.append({"seq": self.seq, "kind": kind, "session": session, **details})
        del self.history[:-HISTORY_LIMIT]


__all__ = ["Breaker", "ENFORCE", "SHADOW"]
