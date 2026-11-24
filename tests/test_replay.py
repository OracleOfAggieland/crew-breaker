"""The replay of the runaway reported on KiroCrew#6338."""

from breaker_core import replay
from breaker_core.replay import (
    CYCLES,
    LOOP,
    OWN_PER_CYCLE,
    REPORTED_BUDGET,
    REPORTED_SUBAGENT_SHARE,
    REPORTED_TOTAL,
    runs_for,
    trace,
)


def test_the_trace_adds_up_to_the_reported_totals():
    own = OWN_PER_CYCLE * CYCLES
    subagents = sum(sum(runs_for(cycle)) for cycle in range(1, CYCLES + 1))
    assert own + subagents == REPORTED_TOTAL
    assert subagents / REPORTED_TOTAL == REPORTED_SUBAGENT_SHARE


def test_every_row_in_the_trace_has_its_own_line():
    lines = [fact.line for _, kind, _, fact in trace() if kind == "row"]
    assert lines == list(range(1, len(lines) + 1))


def test_a_cap_on_the_session_alone_never_trips():
    summary = replay()["summary"]
    assert summary["session_only_total"] == 4_650
    assert summary["session_only_total"] < REPORTED_BUDGET
    assert summary["session_only_tripped"] is False


def test_a_cap_that_counts_subagents_trips_and_drains():
    result = replay()
    summary = result["summary"]
    assert summary["uncapped_total"] == REPORTED_TOTAL
    assert summary["tripped"] is True
    assert summary["tripped_cycle"] == 10
    assert summary["tripped_total"] >= REPORTED_BUDGET
    # Drain: the subagent that was still running finishes, and nothing new starts.
    assert summary["drained_total"] == 5_095
    assert summary["overshoot"] == 95
    assert summary["saved"] == REPORTED_TOTAL - 5_095
    assert result["steps"][-1]["capped"] == 5_095


def test_the_warning_comes_before_the_trip():
    kinds = [kind for step in replay()["steps"] for kind in step["signals"]]
    assert kinds == ["warned", "tripped", "drained"]


def test_the_limit_can_be_changed():
    summary = replay(limit=10_000)["summary"]
    assert summary["tripped_total"] >= 10_000
    assert summary["drained_total"] < 11_000
    assert replay(limit=0)["summary"]["tripped"] is False


def test_steps_name_the_loop_session():
    assert LOOP == "goal-loop"
    assert all(step["cycle"] >= 1 for step in replay()["steps"])
