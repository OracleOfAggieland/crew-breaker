"""Properties of Breaker's core, checked on generated histories.

Each test states one rule the accounting or the cap must keep whatever order
the facts arrive in, and lets Hypothesis look for a history that breaks it.
"""

from __future__ import annotations

import json
import math

from hypothesis import given, settings
from hypothesis import strategies as st

from breaker_core import (
    ENFORCE,
    LABELS,
    SHADOW,
    TRIPPED,
    Breaker,
    Cap,
    Ledger,
    LiveRun,
    Signal,
    Snapshot,
    TurnRow,
    clean_amount,
    stops_for,
)

KEYS = ["s1", "s2", "r1", "r2", "r3", "r4"]
keys = st.sampled_from(KEYS)
good_amounts = st.floats(min_value=0, max_value=5_000, allow_nan=False, allow_infinity=False)
bad_amounts = st.sampled_from([float("nan"), float("inf"), float("-inf"), -1.0, -0.5, "12", None, True, [], {}])
any_amounts = st.one_of(good_amounts, bad_amounts)

rows = st.builds(
    TurnRow,
    shard=st.sampled_from(["a.jsonl", "b.jsonl"]),
    line=st.integers(min_value=0, max_value=40),
    slot=st.one_of(keys, st.just("")),
    credits=any_amounts,
    dollars=any_amounts,
    surface=st.sampled_from(["", "dashboard", "subagent", "cron"]),
)
live_runs = st.builds(LiveRun, session_key=st.one_of(keys, st.just("")), parent=st.one_of(keys, st.just("")), credits=any_amounts)
snapshots = st.builds(Snapshot, runs=st.lists(live_runs, max_size=4).map(tuple))

events = st.one_of(
    st.tuples(st.just("row"), rows),
    st.tuples(st.just("snapshot"), snapshots),
    st.tuples(st.just("cap"), keys, any_amounts, st.sampled_from([SHADOW, ENFORCE, None, "bogus"])),
    st.tuples(st.just("restart"), keys),
    st.tuples(st.just("remove"), keys),
    st.tuples(st.just("unreadable"), st.just("")),
)
histories = st.lists(events, max_size=60)


def apply(breaker: Breaker, event: tuple) -> list[Signal]:
    kind = event[0]
    if kind == "row":
        return breaker.feed_row(event[1])
    if kind == "snapshot":
        return breaker.feed_snapshot(event[1])
    if kind == "cap":
        breaker.set_cap(event[1], event[2], event[3])
        return []
    if kind == "restart":
        return breaker.restart(event[1])
    if kind == "remove":
        breaker.remove_cap(event[1])
        return []
    return breaker.meter_unreadable(event[1])


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


@given(histories)
def test_a_total_never_goes_down(history):
    breaker = Breaker()
    before = {key: 0.0 for key in KEYS}
    for event in history:
        apply(breaker, event)
        for key in KEYS:
            now = breaker.ledger.total(key).total
            assert now >= before[key] - 1e-9, (key, before[key], now)
            before[key] = now


@given(histories)
def test_every_credit_lands_in_exactly_one_session_total(history):
    breaker = Breaker()
    for event in history:
        apply(breaker, event)
    ledger = breaker.ledger
    by_root = sum(ledger.total(root).total for root in ledger.roots())
    assert close(by_root, ledger.grand_total())


@given(st.lists(rows, max_size=60))
def test_a_row_is_counted_once_however_often_it_is_read(row_list):
    ledger = Ledger()
    expected = 0.0
    high_water: dict[str, int] = {}
    for row in row_list:
        ledger.add_row(row)
        if row.slot and row.line > high_water.get(row.shard, 0):
            high_water[row.shard] = row.line
            amount = clean_amount(row.credits)
            if amount is not None:
                expected += amount
    assert close(ledger.grand_total(), expected)

    once = json.dumps(ledger.to_json(), sort_keys=True)
    for row in row_list:
        ledger.add_row(row)
    assert json.dumps(ledger.to_json(), sort_keys=True) == once


@given(
    st.lists(good_amounts, max_size=8),
    st.lists(good_amounts, max_size=8),
    st.randoms(use_true_random=False),
)
def test_a_run_is_never_counted_by_both_its_rows_and_its_live_figure(settled, live, rng):
    ledger = Ledger()
    steps = [("row", amount) for amount in settled] + [("live", amount) for amount in live]
    rng.shuffle(steps)
    line = 0
    for kind, amount in steps:
        if kind == "row":
            line += 1
            ledger.add_row(TurnRow("a.jsonl", line, "run", amount, surface="subagent"))
        else:
            ledger.add_snapshot(Snapshot((LiveRun("run", "parent", amount),)))
    expected = max(sum(settled), max(live, default=0.0))
    assert close(ledger.contribution("run"), expected)

    # Once the link is known, the parent is charged exactly that, not the sum.
    ledger.add_snapshot(Snapshot((LiveRun("run", "parent", 0.0),)))
    assert close(ledger.total("parent").children, expected)
    assert ledger.total("parent").children <= sum(settled) + max(live, default=0.0) + 1e-6


@given(
    st.lists(st.tuples(st.sampled_from(["r1", "r2", "r3"]), good_amounts), max_size=20),
    st.integers(min_value=0, max_value=20),
)
def test_a_link_learned_late_charges_the_same_total(run_rows, position):
    links = Snapshot(tuple(LiveRun(key, "root", 0.0) for key in ["r1", "r2", "r3"]))

    def total_with_link_at(index: int) -> float:
        ledger = Ledger()
        for line, (key, amount) in enumerate(run_rows, start=1):
            if line - 1 == index:
                ledger.add_snapshot(links)
            ledger.add_row(TurnRow("a.jsonl", line, key, amount, surface="subagent"))
        ledger.add_snapshot(links)
        return ledger.total("root").total

    assert close(total_with_link_at(0), total_with_link_at(min(position, len(run_rows))))
    assert close(total_with_link_at(0), sum(amount for _, amount in run_rows))


@given(histories)
def test_a_tripped_cap_stays_tripped_until_the_owner_restarts(history):
    breaker = Breaker()
    tripped: set[str] = set()
    for event in history:
        apply(breaker, event)
        if event[0] in ("restart", "remove"):
            tripped.discard(event[1])
        for session in tripped:
            assert breaker.caps[session].state == TRIPPED, (session, event)
        tripped = {s for s, cap in breaker.caps.items() if cap.state == TRIPPED} | tripped


@given(histories)
def test_a_cap_only_trips_at_or_over_its_limit(history):
    breaker = Breaker()
    for event in history:
        for signal in apply(breaker, event):
            if signal.kind == "tripped":
                assert signal.limit > 0
                assert signal.total >= signal.limit
        for cap in breaker.caps.values():
            if cap.trip is not None:
                assert cap.trip.total >= cap.trip.limit > 0
                assert cap.trip.peak >= cap.trip.total


@given(histories, bad_amounts)
def test_a_bad_meter_reading_moves_nothing_and_trips_nothing(history, garbage):
    breaker = Breaker()
    for event in history:
        apply(breaker, event)
    before = json.dumps(breaker.report()["sessions"], sort_keys=True)

    assert breaker.meter_unreadable("meter down") == []
    for session in KEYS:
        assert breaker.feed_row(TurnRow("z.jsonl", 10_000 + KEYS.index(session), session, garbage)) == []
        assert breaker.feed_snapshot(Snapshot((LiveRun(session, "", garbage),))) is not None
    for cap in breaker.caps.values():
        assert cap.evaluate(garbage, (), breaker.seq) == []

    after = breaker.report()["sessions"]
    assert [(s["session"], s["total"]) for s in after] == [(s["session"], s["total"]) for s in json.loads(before)]


@given(
    st.sampled_from(["warned", "tripped", "drained"]),
    good_amounts,
    good_amounts,
    st.sampled_from(LABELS),
)
def test_shadow_mode_never_stops_anything(kind, total, limit, label):
    signal = Signal(kind, "s1", total, limit)
    assert stops_for(signal, SHADOW, label) == ()
    assert stops_for(signal, "bogus", label) == ()
    if kind != "tripped" or label == "watch":
        assert stops_for(signal, ENFORCE, label) == ()


@given(histories)
def test_raising_the_limit_never_restarts_anything(history):
    breaker = Breaker()
    for event in history:
        apply(breaker, event)
    for session, cap in list(breaker.caps.items()):
        if cap.state == TRIPPED:
            breaker.set_cap(session, cap.limit * 10 + 1_000_000, ENFORCE)
            assert breaker.caps[session].state == TRIPPED
            assert breaker.caps[session].trip is not None


@given(histories)
@settings(max_examples=60)
def test_saving_and_loading_changes_nothing(history):
    breaker = Breaker()
    for event in history:
        apply(breaker, event)
    saved = json.dumps(breaker.to_json(), sort_keys=True)
    loaded = Breaker.from_json(json.loads(saved))
    assert json.dumps(loaded.to_json(), sort_keys=True) == saved
    assert json.dumps(loaded.report()["sessions"], sort_keys=True) == json.dumps(
        breaker.report()["sessions"], sort_keys=True
    )


@given(st.lists(good_amounts, min_size=1, max_size=30), good_amounts.filter(lambda x: x > 0))
def test_a_cap_warns_once_then_trips_once(totals, limit):
    cap = Cap(session="s1", limit=limit, mode=ENFORCE)
    kinds: list[str] = []
    running = 0.0
    for seq, amount in enumerate(totals):
        running += amount
        kinds.extend(signal.kind for signal in cap.evaluate(running, (), seq))
    assert kinds.count("tripped") <= 1
    assert kinds.count("warned") <= 1
    if "warned" in kinds and "tripped" in kinds:
        assert kinds.index("warned") < kinds.index("tripped")
    assert ("tripped" in kinds) == (running >= limit)
