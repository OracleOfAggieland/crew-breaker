"""The attribution ledger: who spent what, and on whose behalf.

Pure accounting. No I/O, no clock, no Kiro Crew imports. The caller feeds it
two kinds of facts and asks for totals:

* a ``TurnRow``: one settled row from Crew's usage log. A row names the session
  the turn ran on (``slot``) and nothing about who started that session.
* a ``Snapshot``: the subagent runs that are running right now, each with the
  session that spawned it and the credits it has billed so far.

The snapshot is the only place the run-to-parent link exists, and it is gone
when the run ends. The ledger keeps the link, so a session's total can include
the subagents it started.

Two rules keep the totals honest:

* **Each credit is counted once.** A run's spend shows up twice: in snapshots
  while it runs, and in rows as its prompts settle. Both describe the same
  credits, so a run contributes ``max(settled rows, highest live figure)``,
  never their sum.
* **A total never goes down.** Rows only add, the highest live figure only
  rises, and a link, once learned, is never changed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

SUBAGENT_SURFACE = "subagent"


@dataclass(frozen=True)
class TurnRow:
    """One settled row of the usage log.

    ``shard`` and ``line`` say where the row sits (file name and 1-based line
    number). The ledger folds each position once, so reading a file again is
    harmless. Lines of one shard must arrive in increasing order.
    """

    shard: str
    line: int
    slot: str
    credits: float
    dollars: float = 0.0
    surface: str = ""
    app: str = ""
    ts: str = ""


@dataclass(frozen=True)
class LiveRun:
    """One running subagent, as a snapshot shows it.

    ``credits`` is cumulative for the run: what has settled plus what the
    prompt in flight has billed so far.
    """

    session_key: str
    parent: str
    credits: float
    run_id: str = ""


@dataclass(frozen=True)
class Snapshot:
    """Every subagent run that is running at one moment."""

    runs: tuple[LiveRun, ...] = ()


@dataclass(frozen=True)
class SessionTotal:
    """What one session has spent, with its subagents."""

    session: str
    own: float
    children: float
    total: float
    dollars: float
    runs: int
    running: tuple[str, ...]


def clean_amount(value: Any) -> float | None:
    """A usable amount, or None when the value can't be trusted.

    Negative, non-finite and non-numeric values are refused rather than
    guessed at: a bad meter reading must never move a total. That includes
    text that happens to look like a number. Crew writes credits as a number,
    so ``"12"`` in that field is a malformed row, not twelve credits.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


class Ledger:
    """Folds rows and snapshots into a spend total per session."""

    def __init__(self) -> None:
        self.high_water: dict[str, int] = {}
        self.settled: dict[str, float] = {}
        self.dollars: dict[str, float] = {}
        self.surface: dict[str, str] = {}
        self.app: dict[str, str] = {}
        self.parent_of: dict[str, str] = {}
        self.live_peak: dict[str, float] = {}
        self.running: set[str] = set()
        self.rows_folded = 0
        self.rows_refused = 0

    # ---- feeding -----------------------------------------------------------

    def add_row(self, row: TurnRow) -> bool:
        """Fold one settled row. Returns False when it changed nothing."""
        if not row.slot or row.line <= self.high_water.get(row.shard, 0):
            return False
        self.high_water[row.shard] = row.line
        credits = clean_amount(row.credits)
        dollars = clean_amount(row.dollars)
        if credits is None:
            self.rows_refused += 1
            return False
        self.rows_folded += 1
        self.settled[row.slot] = self.settled.get(row.slot, 0.0) + credits
        if dollars:
            self.dollars[row.slot] = self.dollars.get(row.slot, 0.0) + dollars
        if row.surface:
            self.surface[row.slot] = row.surface
        if row.app:
            self.app[row.slot] = row.app
        return True

    def add_snapshot(self, snapshot: Snapshot) -> None:
        """Record what is running now, and keep every link it shows."""
        running: set[str] = set()
        for run in snapshot.runs:
            key = run.session_key
            if not key:
                continue
            running.add(key)
            self._learn_link(key, run.parent)
            credits = clean_amount(run.credits)
            if credits is not None and credits > self.live_peak.get(key, 0.0):
                self.live_peak[key] = credits
        self.running = running

    def _learn_link(self, child: str, parent: str) -> None:
        """Keep a run-to-parent link. The first one learned stands.

        A link that would make a session its own ancestor is refused, so a
        total can always be walked to an end.
        """
        if not parent or parent == child or child in self.parent_of:
            return
        if self.root_of(parent) == child:
            return
        self.parent_of[child] = parent

    # ---- reading -----------------------------------------------------------

    def root_of(self, key: str) -> str:
        """The session at the top of the chain that spawned ``key``."""
        seen = {key}
        while key in self.parent_of:
            key = self.parent_of[key]
            if key in seen:
                break
            seen.add(key)
        return key

    def contribution(self, key: str) -> float:
        """What one session spent itself, counting each credit once."""
        return max(self.settled.get(key, 0.0), self.live_peak.get(key, 0.0))

    def keys(self) -> set[str]:
        """Every session the ledger has heard of.

        A session that has only spawned runs so far, with no row of its own
        yet, is still a session: its runs' spend has to land somewhere.
        """
        return set(self.settled) | set(self.live_peak) | set(self.parent_of) | set(self.parent_of.values())

    def descendants(self, session: str) -> list[str]:
        """Every run spawned under ``session``, at any depth."""
        return sorted(k for k in self.parent_of if k != session and self.root_or_ancestor(k, session))

    def root_or_ancestor(self, key: str, ancestor: str) -> bool:
        """Whether ``ancestor`` sits above ``key`` in the spawn chain."""
        seen = {key}
        while key in self.parent_of:
            key = self.parent_of[key]
            if key == ancestor:
                return True
            if key in seen:
                return False
            seen.add(key)
        return False

    def total(self, session: str) -> SessionTotal:
        """The session's own spend plus everything spawned under it."""
        children = self.descendants(session)
        own = self.contribution(session)
        child_spend = sum(self.contribution(k) for k in children)
        dollars = self.dollars.get(session, 0.0) + sum(self.dollars.get(k, 0.0) for k in children)
        running = tuple(k for k in children if k in self.running)
        return SessionTotal(
            session=session,
            own=own,
            children=child_spend,
            total=own + child_spend,
            dollars=dollars,
            runs=len(children),
            running=running,
        )

    def roots(self) -> list[str]:
        """Sessions nobody is known to have spawned."""
        return sorted(k for k in self.keys() if k not in self.parent_of)

    def is_orphan_run(self, key: str) -> bool:
        """A subagent whose parent the ledger never saw."""
        return key not in self.parent_of and self.surface.get(key) == SUBAGENT_SURFACE

    def coverage(self) -> dict[str, float | int]:
        """How much subagent spend the ledger could tie to a parent."""
        linked = [k for k in self.parent_of]
        orphans = [k for k in self.keys() if self.is_orphan_run(k)]
        return {
            "linked_runs": len(linked),
            "linked_credits": sum(self.contribution(k) for k in linked),
            "orphan_runs": len(orphans),
            "orphan_credits": sum(self.contribution(k) for k in orphans),
            "rows_folded": self.rows_folded,
            "rows_refused": self.rows_refused,
        }

    def grand_total(self) -> float:
        """Every credit the ledger knows about, counted once."""
        return sum(self.contribution(k) for k in self.keys())

    # ---- keeping -----------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "high_water": dict(self.high_water),
            "settled": dict(self.settled),
            "dollars": dict(self.dollars),
            "surface": dict(self.surface),
            "app": dict(self.app),
            "parent_of": dict(self.parent_of),
            "live_peak": dict(self.live_peak),
            "running": sorted(self.running),
            "rows_folded": self.rows_folded,
            "rows_refused": self.rows_refused,
        }

    @classmethod
    def from_json(cls, data: Any) -> "Ledger":
        ledger = cls()
        if not isinstance(data, dict):
            return ledger
        ledger.high_water = _int_map(data.get("high_water"))
        ledger.settled = _amount_map(data.get("settled"))
        ledger.dollars = _amount_map(data.get("dollars"))
        ledger.surface = _str_map(data.get("surface"))
        ledger.app = _str_map(data.get("app"))
        ledger.live_peak = _amount_map(data.get("live_peak"))
        for child, parent in _str_map(data.get("parent_of")).items():
            ledger._learn_link(child, parent)
        running = data.get("running")
        ledger.running = {k for k in running if isinstance(k, str)} if isinstance(running, list) else set()
        ledger.rows_folded = _count(data.get("rows_folded"))
        ledger.rows_refused = _count(data.get("rows_refused"))
        return ledger


def _amount_map(data: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            amount = clean_amount(value)
            if isinstance(key, str) and amount is not None:
                out[key] = amount
    return out


def _int_map(data: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                out[key] = value
    return out


def _str_map(data: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, str):
                out[key] = value
    return out


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def fold(ledger: Ledger, rows: Iterable[TurnRow] = (), snapshots: Iterable[Snapshot] = ()) -> Ledger:
    """Feed a batch of rows and snapshots. Handy in tests and the replay."""
    for row in rows:
        ledger.add_row(row)
    for snapshot in snapshots:
        ledger.add_snapshot(snapshot)
    return ledger
