"""The service, run against a usage log on disk and a stand-in gateway."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from backend.meter import MeterError, UsageLog, find_usage_dir, loops_from, snapshot_from
from backend.service import Service


class Ctx:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.logger = None


class FakeGateway:
    """Answers the two routes the service reads."""

    def __init__(self) -> None:
        self.tasks: list[dict[str, Any]] = []
        self.sessions: list[dict[str, Any]] = []
        self.loops: list[dict[str, Any]] = []
        self.down = False

    async def get_json(self, path: str) -> Any:
        if self.down:
            raise MeterError("gateway down")
        if path == "/api/sessions/memory":
            return {"tasks": self.tasks, "sessions": self.sessions}
        return {"loops": self.loops}

    async def close(self) -> None:
        pass


class FakeLoop:
    def __init__(self, loop_id: str, cycle_count: int = 0) -> None:
        self.id = loop_id
        self.cycle_count = cycle_count


class FakeRuns:
    """Stands in for Breaker's own chat slots."""

    available = True

    def __init__(self) -> None:
        self.live: dict[str, FakeLoop] = {}
        self.stops: list[str] = []
        self.armed: list[tuple[str, int]] = []
        self.count = 0

    async def start(self, state: Any, *, prompt: str, title: str, max_cycles: int, idle_secs: int, nudge: str = "") -> dict[str, Any]:
        self.count += 1
        session = f"breaker-{self.count}"
        self.live[session] = FakeLoop(f"loop-{self.count}")
        return {
            "session": session,
            "title": title,
            "max_cycles": max_cycles,
            "idle_secs": idle_secs,
            "nudge": nudge,
            "loop_id": f"loop-{self.count}",
            "loop_note": "",
            "cycles_done": 0,
            "stopped": "",
        }

    async def arm(self, state: Any, record: dict[str, Any], cycles: int) -> tuple[str, str]:
        self.armed.append((record["session"], cycles))
        self.live[record["session"]] = FakeLoop("loop-again")
        return "loop-again", ""

    def loop(self, session: str) -> FakeLoop | None:
        return self.live.get(session)

    async def stop_loop(self, session: str) -> tuple[bool, str]:
        self.stops.append(session)
        self.live.pop(session, None)
        return True, "loop removed"


def write_rows(usage: Path, rows: list[dict[str, Any]], *, shard: str = "2026-11-24.jsonl", torn: str = "") -> None:
    usage.mkdir(parents=True, exist_ok=True)
    with (usage / shard).open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps({"_type": "tokens", **row}) + "\n")
        handle.write(torn)


def make(tmp_path: Path) -> tuple[Service, FakeGateway, FakeRuns, Path]:
    usage = tmp_path / "home" / "usage" / "tokens"
    gateway, runs = FakeGateway(), FakeRuns()
    service = Service(Ctx(tmp_path / "data"), usage_dir=usage, gateway=gateway, runs=runs)
    return service, gateway, runs, usage


def session_of(state: dict[str, Any], key: str) -> dict[str, Any]:
    return next(s for s in state["sessions"] if s["session"] == key)


def test_rows_are_read_once_and_a_torn_line_waits(tmp_path):
    async def scenario() -> None:
        service, _gateway, _runs, usage = make(tmp_path)
        write_rows(usage, [{"slot": "chat-1", "credits": 10, "ts": "2026-11-24T01:00:00Z"}], torn='{"_type": "tokens", "slot": "chat-1", "cre')
        await service.step(live=False)
        await service.step(live=False)
        assert session_of(await service.state(), "chat-1")["total"] == 10

        with (usage / "2026-11-24.jsonl").open("a", encoding="utf-8") as handle:
            handle.write('dits": 5}\n')
        await service.step(live=False)
        assert session_of(await service.state(), "chat-1")["total"] == 15

    asyncio.run(scenario())


def test_a_subagent_is_charged_to_the_session_that_started_it(tmp_path):
    async def scenario() -> None:
        service, gateway, _runs, usage = make(tmp_path)
        gateway.tasks = [{"id": "t1", "session_key": "sub-1", "parent": "chat-1", "credits": 4.0}]
        gateway.sessions = [{"key": "chat-1", "slot_key": "chat-1", "title": "Refactor the parser"}]
        write_rows(usage, [{"slot": "chat-1", "credits": 10}])
        await service.step(live=True)
        row = session_of(await service.state(), "chat-1")
        assert (row["own"], row["children"], row["total"]) == (10, 4.0, 14.0)
        assert row["title"] == "Refactor the parser"
        assert row["running"] == ["sub-1"]

        gateway.tasks = []
        write_rows(usage, [{"slot": "sub-1", "credits": 9, "surface": "subagent"}])
        await service.step(live=True)
        row = session_of(await service.state(), "chat-1")
        assert (row["children"], row["total"], row["running"]) == (9, 19, [])

    asyncio.run(scenario())


def test_a_trip_on_breakers_own_run_removes_its_loop_and_holds(tmp_path):
    async def scenario() -> None:
        service, _gateway, runs, usage = make(tmp_path)
        record = await service.start_run(object(), prompt="go", limit=100, max_cycles=10, idle_secs=60, title="Run", nudge="")
        session = record["session"]
        assert session_of(await service.state(), session)["label"] == "unattended"

        write_rows(usage, [{"slot": session, "credits": 60, "app": "breaker"}])
        await service.step(live=False)
        assert runs.stops == []

        runs.live[session].cycle_count = 3
        write_rows(usage, [{"slot": session, "credits": 60, "app": "breaker"}])
        await service.step(live=False)
        assert runs.stops == [session]
        row = session_of(await service.state(), session)
        assert row["cap"]["state"] == "tripped"
        assert row["run"]["stopped"] == "credit_cap"
        assert row["run"]["cycles_done"] == 3

        # Raising the limit restarts nothing, and a loop that comes back is removed again.
        await service.set_cap(session, 1_000, "enforce", None)
        runs.live[session] = FakeLoop("loop-sneaky")
        await service.step(live=False)
        assert runs.stops == [session, session]
        assert runs.armed == []

        # Only the owner's restart arms the loop again, for the cycles that were left.
        result = await service.restart(session, object())
        assert runs.armed == [(session, 7)]
        assert "armed again" in result["note"]
        assert session_of(await service.state(), session)["cap"]["state"] == "armed"

    asyncio.run(scenario())


def test_a_trip_on_the_owners_loop_waits_for_a_page(tmp_path):
    async def scenario() -> None:
        service, gateway, runs, usage = make(tmp_path)
        gateway.loops = [{"id": "L1", "slot_key": "chat-1", "active": True, "cycle_count": 2, "max_cycles": 50}]
        await service.step(live=True)
        await service.set_cap("chat-1", 50, "enforce", None)
        assert session_of(await service.state(), "chat-1")["label"] == "while_open"

        write_rows(usage, [{"slot": "chat-1", "credits": 80}])
        await service.step(live=False)
        state = await service.state()
        assert runs.stops == []
        assert [a["loop_id"] for a in state["page_actions"]] == ["L1"]

        # Asked once, not once per pass.
        await service.step(live=False)
        assert len((await service.state())["page_actions"]) == 1

        action = state["page_actions"][0]["id"]
        assert await service.page_action_done(action, True, "") is True
        await service.step(live=False)
        assert (await service.state())["page_actions"] == []
        kinds = [e["kind"] for e in await service.history(50)]
        assert "tripped" in kinds and "stopped" in kinds

    asyncio.run(scenario())


def test_shadow_and_watch_stop_nothing(tmp_path):
    async def scenario() -> None:
        service, gateway, runs, usage = make(tmp_path)
        gateway.loops = [{"id": "L1", "slot_key": "looped", "active": True}]
        await service.step(live=True)
        await service.set_cap("looped", 10, "shadow", None)
        await service.set_cap("typed", 10, "enforce", None)
        write_rows(usage, [{"slot": "looped", "credits": 50}, {"slot": "typed", "credits": 50}])
        await service.step(live=False)
        state = await service.state()
        assert session_of(state, "looped")["cap"]["state"] == "tripped"
        assert session_of(state, "typed")["cap"]["state"] == "tripped"
        assert session_of(state, "typed")["label"] == "watch"
        assert state["page_actions"] == [] and runs.stops == []

    asyncio.run(scenario())


def test_an_unreadable_gateway_is_shown_and_trips_nothing(tmp_path):
    async def scenario() -> None:
        service, gateway, _runs, usage = make(tmp_path)
        await service.set_cap("chat-1", 100, "enforce", None)
        write_rows(usage, [{"slot": "chat-1", "credits": 10}])
        gateway.down = True
        await service.step(live=True)
        state = await service.state()
        assert state["meter"]["ok"] is True
        assert state["meter"]["live_ok"] is False
        assert state["capabilities"] == {"chat_slots": True, "live_runs": False, "loops": False}
        assert session_of(state, "chat-1")["cap"]["state"] == "armed"

    asyncio.run(scenario())


def test_state_survives_a_restart(tmp_path):
    async def scenario() -> None:
        service, gateway, runs, usage = make(tmp_path)
        gateway.tasks = [{"id": "t1", "session_key": "sub-1", "parent": "chat-1", "credits": 30}]
        write_rows(usage, [{"slot": "chat-1", "credits": 80}])
        await service.set_cap("chat-1", 100, "shadow", None)
        await service.step(live=True)
        before = await service.state()

        again = Service(Ctx(tmp_path / "data"), usage_dir=usage, gateway=gateway, runs=runs)
        again._load()
        await again.step(live=False)
        after = await again.state()
        assert session_of(after, "chat-1")["total"] == session_of(before, "chat-1")["total"] == 110
        assert session_of(after, "chat-1")["cap"]["state"] == "tripped"
        assert after["coverage"]["rows_folded"] == 1

    asyncio.run(scenario())


def test_the_usage_log_is_found_from_the_data_folder(tmp_path):
    home = tmp_path / "home"
    data = home / "apps" / "breaker" / "data"
    data.mkdir(parents=True)
    (home / "config.json").write_text("{}", encoding="utf-8")
    assert find_usage_dir(data, {}) == home.resolve() / "usage" / "tokens"
    assert find_usage_dir(data, {"KIROCREW_HOME": str(tmp_path)}) == tmp_path / "usage" / "tokens"


def test_a_shard_that_shrinks_is_read_again_without_double_counting(tmp_path):
    usage = tmp_path / "usage"
    write_rows(usage, [{"slot": "a", "credits": 1}, {"slot": "a", "credits": 2}])
    log = UsageLog(usage)
    assert [r.line for r in log.read_new()] == [1, 2]
    (usage / "2026-11-24.jsonl").write_text('{"_type": "tokens", "slot": "a", "credits": 1}\n', encoding="utf-8")
    assert [r.line for r in log.read_new()] == [1]


def test_route_answers_are_read_defensively():
    snapshot, titles = snapshot_from({"tasks": [{"session_key": "r", "parent": "p", "credits": "x"}, "junk", {}], "sessions": [None, {"key": "p", "title": "P"}]})
    assert [(r.session_key, r.parent) for r in snapshot.runs] == [("r", "p")]
    assert titles == {"p": "P"}
    assert loops_from([{"id": "L", "slot_key": "s", "active": False}, {"id": 5}])["s"]["active"] is False
    assert loops_from("nonsense") == {}
