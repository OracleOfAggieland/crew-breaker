"""The runaway reported on KiroCrew#6338, as a trace Breaker can replay.

The report gives totals: a goal loop that carried a 5,000-credit budget in its
own notes spent about 31,000 credits, about 85% of it in subagents. It does
not give a turn-by-turn log. This module builds a trace that adds up to those
totals. **The totals are the report's; the split into cycles and runs is made
up** so there is something to step through.

The trace runs through the same ledger and cap the live app uses, three ways:

* ``session_only``: the loop's own turns only, which is what a session total
  shows when nothing ties a subagent to its parent.
* ``with_subagents``: the loop plus the subagents it started, never stopped.
* ``capped``: the same, with a cap that drains: once it trips, no new cycle
  starts and the subagents already running finish.
"""

from __future__ import annotations

from typing import Any, Iterator

from .breaker import Breaker
from .cap import ENFORCE
from .ledger import LiveRun, Snapshot, TurnRow

REPORTED_TOTAL = 31_000
REPORTED_BUDGET = 5_000
REPORTED_SUBAGENT_SHARE = 0.85
SOURCE_URL = "https://github.com/kirodotdev/KiroCrew/issues/6338"

CYCLES = 62
OWN_PER_CYCLE = 75.0
# Three subagents a cycle. The pattern repeats every three cycles and the last
# two cycles are sized so the whole trace lands on the reported totals.
RUN_PATTERNS: tuple[tuple[float, float, float], ...] = (
    (220.0, 180.0, 120.0),
    (180.0, 145.0, 100.0),
    (140.0, 110.0, 80.0),
)
LAST_CYCLES: tuple[float, float, float] = (180.0, 145.0, 100.0)
LIVE_FRACTION = 0.6

LOOP = "goal-loop"
SHARD = "replay.jsonl"


def runs_for(cycle: int) -> tuple[float, float, float]:
    """What the three subagents of a cycle spend."""
    if cycle > CYCLES - 2:
        return LAST_CYCLES
    return RUN_PATTERNS[(cycle - 1) % len(RUN_PATTERNS)]


def trace() -> Iterator[tuple[int, str, str, Any]]:
    """Yield ``(cycle, kind, label, fact)`` for the whole runaway, in order."""
    line = 0
    for cycle in range(1, CYCLES + 1):
        line += 1
        yield (
            cycle,
            "row",
            "the loop's own turn settles",
            TurnRow(SHARD, line, LOOP, OWN_PER_CYCLE, surface="dashboard"),
        )
        amounts = runs_for(cycle)
        keys = [f"{LOOP}/run-{cycle}-{i + 1}" for i in range(len(amounts))]
        live = [LiveRun(key, LOOP, amount * LIVE_FRACTION) for key, amount in zip(keys, amounts)]
        yield cycle, "snapshot", "three subagents are running", Snapshot(tuple(live))
        for index, (key, amount) in enumerate(zip(keys, amounts)):
            line += 1
            yield (
                cycle,
                "row",
                f"subagent {index + 1} settles",
                TurnRow(SHARD, line, key, amount, surface="subagent"),
            )
            yield cycle, "snapshot", f"subagent {index + 1} is done", Snapshot(tuple(live[index + 1 :]))


def replay(limit: float = REPORTED_BUDGET, warn_pct: int = 80) -> dict[str, Any]:
    """Run the trace three ways and report each step."""
    session_only = Breaker()
    with_subagents = Breaker()
    capped = Breaker()
    for breaker in (session_only, with_subagents, capped):
        breaker.set_cap(LOOP, limit, ENFORCE, warn_pct)

    steps: list[dict[str, Any]] = []
    tripped_cycle: int | None = None
    tripped_total: float | None = None
    capped_stopped = False

    for cycle, kind, label, fact in trace():
        if kind == "row":
            # A session total with no parent link sees only the loop's own rows.
            if fact.slot == LOOP:
                session_only.feed_row(fact)
            with_subagents.feed_row(fact)
        else:
            with_subagents.feed_snapshot(fact)

        signals: list[str] = []
        if not capped_stopped:
            fed = capped.feed_row(fact) if kind == "row" else capped.feed_snapshot(fact)
            for signal in fed:
                signals.append(signal.kind)
                if signal.kind == "tripped":
                    tripped_cycle, tripped_total = cycle, signal.total
            cap = capped.caps[LOOP]
            # Drain: the cycle that tripped finishes, and no new one starts.
            if cap.trip is not None and cap.trip.drained_seq is not None:
                capped_stopped = True

        steps.append(
            {
                "cycle": cycle,
                "what": label,
                "session_only": session_only.ledger.total(LOOP).total,
                "with_subagents": with_subagents.ledger.total(LOOP).total,
                "capped": capped.ledger.total(LOOP).total,
                "signals": signals,
            }
        )

    capped_cap = capped.caps[LOOP]
    only_cap = session_only.caps[LOOP]
    drained_total = capped.ledger.total(LOOP).total
    uncapped_total = with_subagents.ledger.total(LOOP).total
    return {
        "source": {
            "url": SOURCE_URL,
            "reported_total": REPORTED_TOTAL,
            "reported_budget": REPORTED_BUDGET,
            "reported_subagent_share": REPORTED_SUBAGENT_SHARE,
            "note": (
                "The totals are from the report on the issue. The split into "
                "cycles and subagent runs is made up to add up to them."
            ),
        },
        "limit": limit,
        "cycles": CYCLES,
        "steps": steps,
        "summary": {
            "uncapped_total": uncapped_total,
            "session_only_total": session_only.ledger.total(LOOP).total,
            "session_only_state": only_cap.state,
            "session_only_tripped": only_cap.trip is not None,
            "tripped": capped_cap.trip is not None,
            "tripped_cycle": tripped_cycle,
            "tripped_total": tripped_total,
            "drained_total": drained_total,
            "overshoot": capped_cap.trip.overshoot if capped_cap.trip else 0.0,
            "saved": uncapped_total - drained_total,
        },
    }
