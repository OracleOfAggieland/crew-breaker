"""Worked examples for the ledger, the cap and the usage-log reader."""

import json

from backend.breaker_core import (
    ARMED,
    ENFORCE,
    SHADOW,
    TRIPPED,
    UNATTENDED,
    WARNED,
    WATCH,
    WHILE_OPEN,
    Breaker,
    Ledger,
    LiveRun,
    Signal,
    Snapshot,
    TurnRow,
    parse_line,
    split_complete,
    stops_for,
)


def row(line, slot, credits, surface="dashboard", shard="a.jsonl"):
    return TurnRow(shard, line, slot, credits, surface=surface)


def test_a_subagent_is_charged_to_the_session_that_spawned_it():
    ledger = Ledger()
    ledger.add_row(row(1, "chat", 10))
    ledger.add_snapshot(Snapshot((LiveRun("run-a", "chat", 4),)))
    assert ledger.total("chat").total == 14
    ledger.add_row(row(2, "run-a", 30, surface="subagent"))
    ledger.add_snapshot(Snapshot(()))
    total = ledger.total("chat")
    assert (total.own, total.children, total.total, total.runs) == (10, 30, 40, 1)
    assert total.running == ()


def test_a_nested_subagent_rolls_up_to_the_top_session():
    ledger = Ledger()
    ledger.add_snapshot(Snapshot((LiveRun("child", "chat", 0), LiveRun("grandchild", "child", 0))))
    ledger.add_row(row(1, "grandchild", 7, surface="subagent"))
    assert ledger.root_of("grandchild") == "chat"
    assert ledger.total("chat").total == 7
    assert ledger.total("child").total == 7
    assert ledger.roots() == ["chat"]


def test_a_subagent_nobody_saw_running_stays_an_orphan():
    ledger = Ledger()
    ledger.add_row(row(1, "chat", 10))
    ledger.add_row(row(2, "run-b", 25, surface="subagent"))
    assert ledger.total("chat").total == 10
    assert ledger.is_orphan_run("run-b")
    coverage = ledger.coverage()
    assert coverage["orphan_runs"] == 1 and coverage["orphan_credits"] == 25
    assert coverage["linked_runs"] == 0


def test_a_link_cannot_make_a_session_its_own_ancestor():
    ledger = Ledger()
    ledger.add_snapshot(Snapshot((LiveRun("a", "b", 0),)))
    ledger.add_snapshot(Snapshot((LiveRun("b", "a", 0),)))
    assert ledger.parent_of == {"a": "b"}
    assert ledger.root_of("a") == "b"


def test_the_first_link_stands():
    ledger = Ledger()
    ledger.add_snapshot(Snapshot((LiveRun("run", "chat-1", 5),)))
    ledger.add_snapshot(Snapshot((LiveRun("run", "chat-2", 9),)))
    assert ledger.parent_of["run"] == "chat-1"
    assert ledger.total("chat-1").total == 9
    assert ledger.total("chat-2").total == 0


def test_dollars_are_kept_apart_from_credits():
    breaker = Breaker()
    breaker.feed_row(TurnRow("a.jsonl", 1, "claude-chat", 0.0, dollars=1.25))
    session = breaker.report()["sessions"][0]
    assert session["total"] == 0 and session["dollars"] == 1.25
    assert session["bills_in_dollars"] is True


def test_the_cap_warns_trips_and_stays_tripped():
    breaker = Breaker()
    breaker.set_cap("chat", 100, ENFORCE)
    assert breaker.feed_row(row(1, "chat", 50)) == []
    assert [s.kind for s in breaker.feed_row(row(2, "chat", 30))] == ["warned"]
    assert breaker.caps["chat"].state == WARNED
    assert [s.kind for s in breaker.feed_row(row(3, "chat", 30))] == ["tripped"]
    assert breaker.caps["chat"].state == TRIPPED

    breaker.set_cap("chat", 1_000)
    assert breaker.caps["chat"].state == TRIPPED, "raising the limit must not restart"

    assert breaker.restart("chat") == []
    assert breaker.caps["chat"].state == ARMED
    assert len(breaker.caps["chat"].past_trips) == 1


def test_restarting_over_the_limit_trips_again_at_once():
    breaker = Breaker()
    breaker.set_cap("chat", 100, ENFORCE)
    breaker.feed_row(row(1, "chat", 150))
    assert [s.kind for s in breaker.restart("chat")] == ["tripped"]


def test_the_cap_measures_the_overshoot_while_running_work_drains():
    breaker = Breaker()
    breaker.set_cap("chat", 100, SHADOW)
    breaker.feed_snapshot(Snapshot((LiveRun("run", "chat", 0),)))
    signals = breaker.feed_row(row(1, "chat", 100))
    assert [s.kind for s in signals] == ["tripped"]
    assert signals[0].running == ("run",)
    breaker.feed_row(row(2, "run", 40, surface="subagent"))
    drained = breaker.feed_snapshot(Snapshot(()))
    assert [s.kind for s in drained] == ["drained"]
    assert drained[0].overshoot == 40
    assert breaker.caps["chat"].trip.overshoot == 40


def test_a_cap_of_zero_is_no_cap():
    breaker = Breaker()
    breaker.set_cap("chat", 0, ENFORCE)
    assert breaker.feed_row(row(1, "chat", 10_000)) == []
    assert breaker.caps["chat"].state == ARMED


def test_setting_a_cap_below_what_is_already_spent_trips_it():
    breaker = Breaker()
    breaker.feed_row(row(1, "chat", 500))
    breaker.set_cap("chat", 100, ENFORCE)
    assert breaker.caps["chat"].state == TRIPPED


def test_only_an_enforced_trip_stops_anything_and_only_by_its_label():
    trip = Signal("tripped", "chat", 120, 100)
    assert stops_for(trip, ENFORCE, UNATTENDED) == ("stop_own_loop",)
    assert stops_for(trip, ENFORCE, WHILE_OPEN) == ("pause_loop_from_page",)
    assert stops_for(trip, ENFORCE, WATCH) == ()
    assert stops_for(trip, SHADOW, UNATTENDED) == ()
    assert stops_for(Signal("warned", "chat", 80, 100), ENFORCE, UNATTENDED) == ()


def test_the_history_records_what_happened():
    breaker = Breaker()
    breaker.set_cap("chat", 100, ENFORCE)
    breaker.feed_row(row(1, "chat", 120))
    kinds = [entry["kind"] for entry in breaker.history]
    assert kinds == ["cap_set", "tripped"]
    assert breaker.history[-1]["mode"] == ENFORCE


def test_a_usage_line_is_read_and_a_torn_one_is_left():
    line = json.dumps(
        {"_type": "tokens", "ts": "2026-11-24T01:02:03+00:00", "slot": "chat", "app": "", "credits": 2.5, "cost": 0.0, "surface": "subagent"}
    )
    parsed = parse_line("2026-11-24.jsonl", 3, line)
    assert parsed is not None
    assert (parsed.slot, parsed.credits, parsed.surface, parsed.line) == ("chat", 2.5, "subagent", 3)

    assert parse_line("s", 1, line[:20]) is None
    assert parse_line("s", 1, "") is None
    assert parse_line("s", 1, "[1, 2]") is None
    assert parse_line("s", 1, json.dumps({"_type": "other", "slot": "chat"})) is None
    assert parse_line("s", 1, json.dumps({"credits": 1})) is None


def test_only_whole_lines_are_handed_on():
    assert split_complete("") == ([], "")
    assert split_complete("one\ntwo\nthr") == (["one", "two"], "thr")
    assert split_complete("one\n") == (["one"], "")
