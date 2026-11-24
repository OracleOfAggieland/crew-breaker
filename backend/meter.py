"""Reading the meter: Crew's usage log on disk, and its live routes.

Two sources, and neither is private to Crew:

* the usage log, ``usage/tokens/YYYY-MM-DD.jsonl`` under the data home, one
  line per finished turn;
* the gateway's own REST routes, called with this app's token, for the
  subagents running right now and the goal loops.

Nothing here decides anything. It hands rows and snapshots to the caller.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .breaker_core import LiveRun, Snapshot, TurnRow, parse_line

READ_LIMIT = 8 * 1024 * 1024  # bytes of one shard read in one pass
DEFAULT_HOME = Path.home() / ".kiro" / "crew"


class MeterError(Exception):
    """The meter could not be read."""


def find_usage_dir(data_dir: Path, environ: Mapping[str, str] | None = None) -> Path:
    """Where this gateway keeps its usage log.

    The data home is the folder ``KIROCREW_HOME`` names, else the ancestor of
    the app's data folder that holds Crew's ``config.json``, else the default.
    """
    environ = os.environ if environ is None else environ
    named = environ.get("KIROCREW_HOME", "").strip()
    if named and Path(named).is_dir():
        return Path(named) / "usage" / "tokens"
    for ancestor in Path(data_dir).resolve().parents:
        if (ancestor / "usage").is_dir() or (ancestor / "config.json").is_file():
            return ancestor / "usage" / "tokens"
    return DEFAULT_HOME / "usage" / "tokens"


class UsageLog:
    """Reads new whole lines from the usage log, remembering where it stopped."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.positions: dict[str, dict[str, int]] = {}

    def read_new(self) -> list[TurnRow]:
        """Every row written since the last call. Blocking: call it off the event loop.

        A missing folder means no turn has finished yet, and reads as no rows.
        Anything else that stops the read raises :class:`MeterError`.
        """
        try:
            if not self.directory.is_dir():
                return []
            shards = sorted(p for p in self.directory.iterdir() if p.suffix == ".jsonl" and p.is_file())
        except OSError as exc:
            raise MeterError(f"can't list the usage log: {exc}") from exc
        rows: list[TurnRow] = []
        for shard in shards:
            rows.extend(self._read_shard(shard))
        return rows

    def _read_shard(self, path: Path) -> list[TurnRow]:
        name = path.name
        position = self.positions.get(name) or {"offset": 0, "line": 0}
        try:
            size = path.stat().st_size
            if size < position["offset"]:
                # The file was replaced by a shorter one. Start over; the ledger
                # folds each line number once, so nothing is counted twice.
                position = {"offset": 0, "line": 0}
            if size == position["offset"]:
                self.positions[name] = position
                return []
            with path.open("rb") as handle:
                handle.seek(position["offset"])
                data = handle.read(READ_LIMIT)
        except OSError as exc:
            raise MeterError(f"can't read {name}: {exc}") from exc
        end = data.rfind(b"\n")
        if end < 0:
            return []  # a row caught mid-write; wait for its newline
        rows: list[TurnRow] = []
        line = position["line"]
        for raw in data[: end + 1].split(b"\n")[:-1]:
            line += 1
            row = parse_line(name, line, raw.decode("utf-8", "replace"))
            if row is not None:
                rows.append(row)
        self.positions[name] = {"offset": position["offset"] + end + 1, "line": line}
        return rows

    def to_json(self) -> dict[str, Any]:
        return {name: dict(position) for name, position in self.positions.items()}

    def load(self, data: Any) -> None:
        self.positions = {}
        if not isinstance(data, dict):
            return
        for name, position in data.items():
            if not isinstance(name, str) or not isinstance(position, dict):
                continue
            offset, line = position.get("offset"), position.get("line")
            if _count(offset) and _count(line):
                self.positions[name] = {"offset": offset, "line": line}


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class Gateway:
    """Calls the gateway's REST routes with this app's own token."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx
        self._http: Any = None
        self._token = ""

    async def close(self) -> None:
        if self._http is not None:
            await self._http.close()
            self._http = None

    async def get_json(self, path: str) -> Any:
        """GET one route. Raises :class:`MeterError` when it can't be read."""
        import aiohttp  # the gateway ships it; imported late so tests need not

        origin_of = getattr(self._ctx, "gateway_origin", None)
        token_of = getattr(self._ctx, "app_token", None)
        if not callable(origin_of) or not callable(token_of):
            raise MeterError("this Crew gives an app no way to call the gateway")
        origin = origin_of()
        if not origin:
            raise MeterError("the gateway gives no local address to call")
        if self._http is None:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        port = urlsplit(origin).port
        for attempt in (1, 2):
            if not self._token:
                self._token = await token_of()
            if not self._token:
                raise MeterError("no app token: is Breaker enabled?")
            try:
                async with self._http.get(
                    f"{origin}{path}", cookies={f"mc_token_{port}": self._token}
                ) as response:
                    if response.status in (401, 403) and attempt == 1:
                        self._token = ""
                        continue
                    if response.status != 200:
                        raise MeterError(f"{path} answered {response.status}")
                    return await response.json()
            except MeterError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure is "unreadable"
                raise MeterError(f"{path}: {type(exc).__name__}") from exc
        raise MeterError(f"{path} refused this app's token")


def snapshot_from(payload: Any) -> tuple[Snapshot, dict[str, str]]:
    """Read ``GET /api/sessions/memory``: the running subagents, and session titles."""
    if not isinstance(payload, dict):
        raise MeterError("the running-sessions route answered something unexpected")
    runs: list[LiveRun] = []
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if not isinstance(task, dict):
                continue
            key = task.get("session_key")
            if not isinstance(key, str) or not key:
                continue
            parent = task.get("parent")
            runs.append(
                LiveRun(
                    session_key=key,
                    parent=parent if isinstance(parent, str) else "",
                    credits=task.get("credits"),
                    run_id=str(task.get("id") or ""),
                )
            )
    titles: dict[str, str] = {}
    sessions = payload.get("sessions")
    if isinstance(sessions, list):
        for session in sessions:
            if not isinstance(session, dict):
                continue
            title = session.get("title")
            if not isinstance(title, str) or not title:
                continue
            for field in ("key", "slot_key"):
                key = session.get(field)
                if isinstance(key, str) and key and title != key:
                    titles[key] = title
    return Snapshot(tuple(runs)), titles


def loops_from(payload: Any) -> dict[str, dict[str, Any]]:
    """Read ``GET /api/autonudge``: the goal loop on each session, by session key."""
    items: Any = payload
    if isinstance(payload, dict):
        items = payload.get("loops") or payload.get("nudges") or payload.get("data") or payload.get("items") or []
    loops: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        return loops
    for item in items:
        if not isinstance(item, dict):
            continue
        key, loop_id = item.get("slot_key"), item.get("id")
        if not isinstance(key, str) or not key or not isinstance(loop_id, str) or not loop_id:
            continue
        loops[key] = {
            "id": loop_id,
            "active": bool(item.get("active", True)),
            "cycle_count": item.get("cycle_count") if _count(item.get("cycle_count")) else 0,
            "max_cycles": item.get("max_cycles") if _count(item.get("max_cycles")) else 0,
            "source": item.get("source") if isinstance(item.get("source"), str) else "",
        }
    return loops
