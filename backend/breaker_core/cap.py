"""The cap: a credit limit on one session and the subagents it started.

Pure state machine. It is handed a total and answers with what changed. It
never stops anything itself; the caller decides what a trip means.

The rules follow the request for change it prototypes (KiroCrew#35488):

* ``limit`` of 0 means no cap.
* The cap warns once, at ``warn_pct`` of the limit.
* It trips when the total reaches the limit, and **stays tripped** until the
  owner restarts the work. Raising the limit does not restart anything.
* After a trip it keeps watching, to measure how far spend ran past the limit
  while the work that was already running drained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ledger import clean_amount

ARMED = "armed"
WARNED = "warned"
TRIPPED = "tripped"

SHADOW = "shadow"
ENFORCE = "enforce"

# How well Breaker can hold a cap on a given session.
UNATTENDED = "unattended"  # Breaker owns the work and can stop it by itself
WHILE_OPEN = "while_open"  # needs the owner's authority, so a Breaker page must be open
WATCH = "watch"  # Breaker can only tell the owner

LABELS = (UNATTENDED, WHILE_OPEN, WATCH)


@dataclass(frozen=True)
class Signal:
    """One thing that just changed about a cap."""

    kind: str  # "warned" | "tripped" | "drained"
    session: str
    total: float
    limit: float
    overshoot: float = 0.0
    running: tuple[str, ...] = ()


@dataclass
class Trip:
    """A trip, and what happened after it."""

    seq: int
    total: float
    limit: float
    running: tuple[str, ...]
    peak: float
    drained_seq: int | None = None

    @property
    def overshoot(self) -> float:
        return max(0.0, self.peak - self.limit)

    def to_json(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "total": self.total,
            "limit": self.limit,
            "running": list(self.running),
            "peak": self.peak,
            "drained_seq": self.drained_seq,
            "overshoot": self.overshoot,
        }

    @classmethod
    def from_json(cls, data: Any) -> "Trip | None":
        if not isinstance(data, dict):
            return None
        total = clean_amount(data.get("total"))
        limit = clean_amount(data.get("limit"))
        peak = clean_amount(data.get("peak"))
        seq = data.get("seq")
        if total is None or limit is None or peak is None or not isinstance(seq, int):
            return None
        running = data.get("running")
        drained = data.get("drained_seq")
        return cls(
            seq=seq,
            total=total,
            limit=limit,
            running=tuple(k for k in running if isinstance(k, str)) if isinstance(running, list) else (),
            peak=peak,
            drained_seq=drained if isinstance(drained, int) else None,
        )


@dataclass
class Cap:
    """A credit limit on one session."""

    session: str
    limit: float = 0.0
    mode: str = SHADOW
    warn_pct: int = 80
    state: str = ARMED
    trip: Trip | None = None
    past_trips: list[Trip] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.limit > 0

    def set(self, limit: Any, mode: str | None = None, warn_pct: Any = None) -> None:
        """Change the limit, the mode or the warning mark.

        A tripped cap stays tripped whatever the new limit is. Only
        ``restart`` clears a trip.
        """
        amount = clean_amount(limit)
        if amount is not None:
            self.limit = amount
        if mode in (SHADOW, ENFORCE):
            self.mode = mode
        if isinstance(warn_pct, int) and not isinstance(warn_pct, bool) and 1 <= warn_pct <= 100:
            self.warn_pct = warn_pct

    def restart(self) -> None:
        """The owner restarted the work: arm the cap again."""
        if self.trip is not None:
            self.past_trips.append(self.trip)
            del self.past_trips[:-20]
        self.trip = None
        self.state = ARMED

    def evaluate(self, total: Any, running: tuple[str, ...], seq: int) -> list[Signal]:
        """Look at the session's total and report what changed.

        An unusable total changes nothing: Breaker fails open.
        """
        amount = clean_amount(total)
        if amount is None or not self.active:
            return []
        if self.state == TRIPPED and self.trip is not None:
            return self._after_trip(amount, running, seq)
        if amount >= self.limit:
            self.state = TRIPPED
            self.trip = Trip(seq=seq, total=amount, limit=self.limit, running=running, peak=amount)
            signals = [Signal("tripped", self.session, amount, self.limit, 0.0, running)]
            if not running:
                self.trip.drained_seq = seq
            return signals
        if self.state == ARMED and amount >= self.limit * self.warn_pct / 100:
            self.state = WARNED
            return [Signal("warned", self.session, amount, self.limit)]
        return []

    def _after_trip(self, amount: float, running: tuple[str, ...], seq: int) -> list[Signal]:
        trip = self.trip
        assert trip is not None
        if amount > trip.peak:
            trip.peak = amount
        if trip.drained_seq is None and not running:
            trip.drained_seq = seq
            return [Signal("drained", self.session, amount, trip.limit, trip.overshoot)]
        return []

    def to_json(self) -> dict[str, Any]:
        return {
            "session": self.session,
            "limit": self.limit,
            "mode": self.mode,
            "warn_pct": self.warn_pct,
            "state": self.state,
            "trip": self.trip.to_json() if self.trip else None,
            "past_trips": [t.to_json() for t in self.past_trips],
        }

    @classmethod
    def from_json(cls, data: Any) -> "Cap | None":
        if not isinstance(data, dict) or not isinstance(data.get("session"), str):
            return None
        cap = cls(session=data["session"])
        cap.set(data.get("limit"), data.get("mode"), data.get("warn_pct"))
        trip = Trip.from_json(data.get("trip"))
        state = data.get("state")
        if state == TRIPPED and trip is not None:
            cap.state, cap.trip = TRIPPED, trip
        elif state == WARNED:
            cap.state = WARNED
        past = data.get("past_trips")
        if isinstance(past, list):
            cap.past_trips = [t for t in (Trip.from_json(p) for p in past) if t is not None][-20:]
        return cap


def stops_for(signal: Signal, mode: str, label: str) -> tuple[str, ...]:
    """What Breaker should do about a signal.

    Only a trip in enforce mode stops anything, and only by the means the
    label allows. Everything already running is left to finish.
    """
    if signal.kind != "tripped" or mode != ENFORCE:
        return ()
    if label == UNATTENDED:
        return ("stop_own_loop",)
    if label == WHILE_OPEN:
        return ("pause_loop_from_page",)
    return ()
