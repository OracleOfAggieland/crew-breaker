"""Breaker's running service: reads the meter, keeps the ledger, holds the caps.

One service per gateway. It lives in this module, not in the hook entry file:
Crew runs the entry file again for each hook that names it, so anything kept
there would exist three times. A sibling module is imported once.

The service does four things on a timer:

1. reads the rows Crew has added to its usage log;
2. every so often, asks the gateway which subagents are running and which
   goal loops exist;
3. feeds both to the core, which says which caps warned, tripped or drained;
4. holds every tripped cap that is in enforce mode, by the means its label
   allows.

Nothing here cuts a running turn, and nothing here refuses a typed message.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .breaker_core import ENFORCE, SHADOW, TRIPPED, UNATTENDED, WATCH, WHILE_OPEN, Breaker, Signal, stops_for
from .meter import Gateway, MeterError, UsageLog, find_usage_dir, loops_from, snapshot_from
from .runs import STOP_REASON, RunRefused, Runs

VERSION = "0.1.0"
POLL_SECS = 5.0
LIVE_SECS = 10.0
SAVE_FILE = "breaker.json"
EVENT_LIMIT = 500
PAGE_RETRY_SECS = 60.0
LOOPS_ROUTE = "/api/autonudge"
LIVE_ROUTE = "/api/sessions/memory"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Service:
    """The ledger, the caps and the loop that keeps them current."""

    def __init__(self, ctx: Any, *, usage_dir: Path | None = None, gateway: Any = None, runs: Any = None) -> None:
        self.ctx = ctx
        self.data_dir = Path(ctx.data_dir)
        self.breaker = Breaker()
        self.log = UsageLog(usage_dir or find_usage_dir(self.data_dir))
        self.gateway = gateway or Gateway(ctx)
        self.runs_sdk = runs or Runs(ctx)
        self.lock = asyncio.Lock()
        self.titles: dict[str, str] = {}
        self.last_spend: dict[str, str] = {}
        self.loops: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.page_actions: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.meter: dict[str, Any] = {"ok": True, "note": "", "last_read": "", "live_ok": True, "live_note": ""}
        self.loops_ok = True
        self._seen_seq = 0
        self._action_count = 0
        self._page_retry: dict[str, float] = {}
        self._live_due = 0.0
        self._dirty = False
        self._task: asyncio.Task[Any] | None = None
        self._loaded = False

    # ---- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Load what was saved and start the timer. Safe to call twice."""
        if self._task is not None and not self._task.done():
            return
        if not self._loaded:
            await asyncio.to_thread(self._load)
            self._loaded = True
        self._task = asyncio.create_task(self._run(), name="breaker-meter")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - stopping must not raise
                pass
        async with self.lock:
            await asyncio.to_thread(self._save)
        await self.gateway.close()

    async def _run(self) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad pass must not end the meter
                self.meter.update(ok=False, note=f"a pass failed: {type(exc).__name__}: {exc}")
                self._log("warning", "Breaker: a meter pass failed: %s", exc)
            await asyncio.sleep(POLL_SECS)

    # ---- one pass ----------------------------------------------------------

    async def step(self, *, live: bool | None = None) -> None:
        """Read the meter once and act on what changed."""
        due = time.monotonic() >= self._live_due if live is None else live
        live_read: tuple[Any, Any] | None = None
        if due:
            # Asked before the lock is taken: a slow answer must not hold up the page.
            self._live_due = time.monotonic() + LIVE_SECS
            live_read = (await self._get(LIVE_ROUTE), await self._get(LOOPS_ROUTE))
        async with self.lock:
            signals = await asyncio.to_thread(self._read_rows)
            if live_read is not None:
                signals += self._fold_live(*live_read)
            self._drain_history()  # the trip is noted before the stop it causes
            await self._act(signals)
            await self._hold()
            self._drain_history()
            if self._dirty:
                await asyncio.to_thread(self._save)

    async def _get(self, route: str) -> Any:
        """One gateway route's answer, or the error that stopped the read."""
        try:
            return await self.gateway.get_json(route)
        except MeterError as exc:
            return exc

    def _read_rows(self) -> list[Signal]:
        try:
            rows = self.log.read_new()
        except MeterError as exc:
            self.breaker.meter_unreadable(str(exc))
            self.meter.update(ok=False, note=str(exc))
            return []
        self.meter.update(ok=True, note="", last_read=now_iso())
        signals: list[Signal] = []
        for row in rows:
            if row.ts:
                self.last_spend[row.slot] = row.ts
            signals.extend(self.breaker.feed_row(row))
        if rows:
            self._dirty = True
        return signals

    def _fold_live(self, running: Any, loops: Any) -> list[Signal]:
        signals: list[Signal] = []
        try:
            if isinstance(running, MeterError):
                raise running
            snapshot, titles = snapshot_from(running)
        except MeterError as exc:
            self.meter.update(live_ok=False, live_note=str(exc))
        else:
            self.meter.update(live_ok=True, live_note="")
            self.titles.update(titles)
            signals = self.breaker.feed_snapshot(snapshot)
            if snapshot.runs:
                self._dirty = True
        if isinstance(loops, MeterError):
            self.loops_ok = False
        else:
            self.loops, self.loops_ok = loops_from(loops), True
        return signals

    # ---- holding caps ------------------------------------------------------

    def label_of(self, session: str) -> str:
        """How well a cap on this session can be held right now."""
        if session in self.runs and self.runs_sdk.available:
            return UNATTENDED
        loop = self.loops.get(session)
        if loop is not None and loop.get("active"):
            return WHILE_OPEN
        return WATCH

    async def _act(self, signals: list[Signal]) -> None:
        for signal in signals:
            cap = self.breaker.caps.get(signal.session)
            if cap is None:
                continue
            for stop in stops_for(signal, cap.mode, self.label_of(signal.session)):
                if stop == "stop_own_loop":
                    await self._stop_own(signal.session)
                elif stop == "pause_loop_from_page":
                    self._queue_pause(signal.session)

    async def _hold(self) -> None:
        """Keep every tripped, enforced cap held: a trip lasts until the owner restarts."""
        for session, cap in self.breaker.caps.items():
            if cap.state != TRIPPED or cap.mode != ENFORCE or not cap.active:
                continue
            label = self.label_of(session)
            if label == UNATTENDED:
                if self.runs_sdk.loop(session) is not None:
                    await self._stop_own(session)
            elif label == WHILE_OPEN:
                self._queue_pause(session)

    async def _stop_own(self, session: str) -> None:
        run = self.runs.get(session)
        if run is None:
            return
        loop = self.runs_sdk.loop(session)
        if loop is not None:
            done = getattr(loop, "cycle_count", None)
            if isinstance(done, int) and not isinstance(done, bool):
                run["cycles_done"] = int(run.get("cycles_done") or 0) + done
        stopped, note = await self.runs_sdk.stop_loop(session)
        first = run.get("stopped") != STOP_REASON
        if stopped:
            run["stopped"], run["loop_id"] = STOP_REASON, ""
            if loop is not None or first:
                self._event("stopped", session, detail=f"{note}; a turn already running is left to finish")
        elif run.get("stop_note") != note:
            self._event("stop_failed", session, detail=note)
        run["stop_note"] = note
        self._dirty = True

    def _queue_pause(self, session: str) -> None:
        loop = self.loops.get(session)
        if loop is None or not loop.get("active"):
            return
        loop_id = str(loop["id"])
        if any(a["loop_id"] == loop_id for a in self.page_actions.values()):
            return
        if time.monotonic() < self._page_retry.get(loop_id, 0.0):
            return
        self._action_count += 1
        action_id = f"a{self._action_count}"
        self.page_actions[action_id] = {
            "id": action_id,
            "kind": "pause_loop",
            "session": session,
            "loop_id": loop_id,
            "reason": STOP_REASON,
            "queued_at": now_iso(),
        }
        self._event("page_action_queued", session, detail="waiting for an open Breaker page to pause the loop")
        self._dirty = True

    # ---- the owner's moves -------------------------------------------------

    async def set_cap(self, session: str, limit: Any, mode: Any, warn_pct: Any) -> dict[str, Any]:
        async with self.lock:
            cap = self.breaker.set_cap(session, limit, mode if mode in (SHADOW, ENFORCE) else None, warn_pct)
            self._drain_history()
            await self._hold()
            self._drain_history()
            self._dirty = True
            await asyncio.to_thread(self._save)
            return cap.to_json()

    async def remove_cap(self, session: str) -> None:
        async with self.lock:
            self.breaker.remove_cap(session)
            self._drop_actions(session)
            self._drain_history()
            self._dirty = True
            await asyncio.to_thread(self._save)

    async def restart(self, session: str, state: Any = None) -> dict[str, Any]:
        """The owner restarts the work under a cap. Over the limit, it trips again at once."""
        async with self.lock:
            signals = self.breaker.restart(session)
            self._drop_actions(session)
            note = ""
            cap = self.breaker.caps.get(session)
            run = self.runs.get(session)
            if run is not None and run.get("stopped") == STOP_REASON and cap is not None and cap.state != TRIPPED:
                left = int(run.get("max_cycles") or 0) - int(run.get("cycles_done") or 0)
                if left > 0 and state is not None:
                    loop_id, note = await self.runs_sdk.arm(state, run, left)
                    if loop_id:
                        run["loop_id"], run["stopped"], run["stop_note"] = loop_id, "", ""
                        note = f"loop armed again for {left} more cycle{'s' if left != 1 else ''}"
                elif left <= 0:
                    run["stopped"] = ""
                    note = "no cycles were left, so no loop was armed"
            self._drain_history()
            await self._act(signals)
            await self._hold()
            self._dirty = True
            await asyncio.to_thread(self._save)
            return {"signals": [s.kind for s in signals], "note": note}

    async def start_run(self, state: Any, *, prompt: str, limit: Any, max_cycles: int, idle_secs: int, title: str, nudge: str) -> dict[str, Any]:
        """Start work Breaker owns, with an enforced cap on it from the first turn."""
        async with self.lock:
            record = await self.runs_sdk.start(
                state, prompt=prompt, title=title, max_cycles=max_cycles, idle_secs=idle_secs, nudge=nudge
            )
            record["started_at"] = now_iso()
            session = record["session"]
            self.runs[session] = record
            self.titles[session] = title
            self.breaker.set_cap(session, limit, ENFORCE)
            self._event("run_started", session, limit=self.breaker.caps[session].limit, detail=record.get("loop_note") or "")
            self._drain_history()
            self._dirty = True
            await asyncio.to_thread(self._save)
            return record

    async def stop_run(self, session: str) -> tuple[bool, str]:
        """The owner ends one of Breaker's runs: its loop is removed, its turn left to finish."""
        async with self.lock:
            run = self.runs.get(session)
            if run is None:
                return False, "not one of Breaker's runs"
            stopped, note = await self.runs_sdk.stop_loop(session)
            if stopped:
                run["stopped"], run["loop_id"] = "owner", ""
                self._event("stopped", session, detail=f"by the owner: {note}")
            self._dirty = True
            await asyncio.to_thread(self._save)
            return stopped, note

    async def page_action_done(self, action_id: str, ok: bool, detail: str) -> bool:
        async with self.lock:
            action = self.page_actions.pop(action_id, None)
            if action is None:
                return False
            session, loop_id = action["session"], action["loop_id"]
            if ok:
                loop = self.loops.get(session)
                if loop is not None and loop.get("id") == loop_id:
                    loop["active"] = False
                self._event("stopped", session, detail=detail or "loop paused from the page; the running turn is left to finish")
            else:
                self._page_retry[loop_id] = time.monotonic() + PAGE_RETRY_SECS
                self._event("stop_failed", session, detail=detail or "the page could not pause the loop")
            self._dirty = True
            await asyncio.to_thread(self._save)
            return True

    def _drop_actions(self, session: str) -> None:
        for action_id in [k for k, a in self.page_actions.items() if a["session"] == session]:
            del self.page_actions[action_id]

    # ---- reading -----------------------------------------------------------

    async def state(self) -> dict[str, Any]:
        async with self.lock:
            return await asyncio.to_thread(self._state)

    def _state(self) -> dict[str, Any]:
        report = self.breaker.report()
        ledger = self.breaker.ledger
        sessions = []
        for item in report["sessions"]:
            key = item["session"]
            newest = max([self.last_spend.get(k, "") for k in [key, *ledger.descendants(key)]] or [""])
            run = self.runs.get(key)
            loop = self.loops.get(key)
            sessions.append(
                {
                    **item,
                    "title": self.titles.get(key, ""),
                    "last_spend": newest,
                    "owned": run is not None,
                    "run": _public_run(run) if run is not None else None,
                    "label": self.label_of(key),
                    "loop": dict(loop) if loop is not None else None,
                }
            )
        sessions.sort(key=lambda s: (s["last_spend"], s["total"]), reverse=True)
        return {
            "version": VERSION,
            "now": now_iso(),
            "usage_log": str(self.log.directory),
            "meter": dict(self.meter),
            "capabilities": {
                "chat_slots": self.runs_sdk.available,
                "live_runs": bool(self.meter["live_ok"]),
                "loops": self.loops_ok,
            },
            "sessions": sessions,
            "coverage": report["coverage"],
            "grand_total": report["grand_total"],
            "page_actions": list(self.page_actions.values()),
        }

    async def history(self, limit: int) -> list[dict[str, Any]]:
        async with self.lock:
            return list(reversed(self.events[-max(1, min(limit, EVENT_LIMIT)) :]))

    # ---- inside ------------------------------------------------------------

    def _drain_history(self) -> None:
        """Copy what the core noted since the last look, with the time on it."""
        for entry in self.breaker.history:
            if entry.get("seq", 0) > self._seen_seq:
                details = {k: v for k, v in entry.items() if k not in ("seq", "kind", "session")}
                self._event(str(entry.get("kind")), str(entry.get("session")), seq=entry.get("seq"), **details)
        self._seen_seq = self.breaker.seq

    def _event(self, kind: str, session: str, **details: Any) -> None:
        self.events.append({"at": now_iso(), "kind": kind, "session": session, **details})
        del self.events[:-EVENT_LIMIT]
        self._dirty = True

    def _log(self, level: str, message: str, *args: Any) -> None:
        logger = getattr(self.ctx, "logger", None)
        method = getattr(logger, level, None)
        if callable(method):
            method(message, *args)

    def _save(self) -> None:
        data = {
            "version": 1,
            "breaker": self.breaker.to_json(),
            "log": self.log.to_json(),
            "titles": self.titles,
            "last_spend": self.last_spend,
            "runs": self.runs,
            "page_actions": self.page_actions,
            "action_count": self._action_count,
            "events": self.events,
            "seen_seq": self._seen_seq,
        }
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            target = self.data_dir / SAVE_FILE
            scratch = self.data_dir / (SAVE_FILE + ".tmp")
            scratch.write_text(json.dumps(data), encoding="utf-8")
            os.replace(scratch, target)
            self._dirty = False
        except OSError as exc:
            self._log("warning", "Breaker: could not save its state: %s", exc)

    def _load(self) -> None:
        try:
            data = json.loads((self.data_dir / SAVE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.breaker = Breaker.from_json(data.get("breaker"))
        self.log.load(data.get("log"))
        self.titles = _str_map(data.get("titles"))
        self.last_spend = _str_map(data.get("last_spend"))
        self.runs = _dict_map(data.get("runs"))
        self.page_actions = _dict_map(data.get("page_actions"))
        count = data.get("action_count")
        self._action_count = count if isinstance(count, int) and count >= 0 else len(self.page_actions)
        events = data.get("events")
        self.events = [e for e in events if isinstance(e, dict)][-EVENT_LIMIT:] if isinstance(events, list) else []
        seen = data.get("seen_seq")
        self._seen_seq = seen if isinstance(seen, int) and seen >= 0 else self.breaker.seq


def _public_run(run: dict[str, Any]) -> dict[str, Any]:
    keys = ("title", "max_cycles", "idle_secs", "loop_id", "loop_note", "cycles_done", "stopped", "stop_note", "started_at")
    return {k: run.get(k) for k in keys}


def _str_map(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _dict_map(data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)}


# One service per gateway process, shared by every hook and every route handler.
_SERVICE: Service | None = None


def service_for(ctx: Any) -> Service:
    """The gateway's one Breaker service, made on first use."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = Service(ctx)
    return _SERVICE


async def shut_down() -> None:
    """Stop the service and forget it, so a later enable starts clean."""
    global _SERVICE
    service, _SERVICE = _SERVICE, None
    if service is not None:
        await service.stop()


__all__ = ["RunRefused", "Service", "WATCH", "service_for", "shut_down"]
