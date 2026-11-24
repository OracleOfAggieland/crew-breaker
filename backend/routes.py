"""Breaker's HTTP routes and lifecycle hooks, served inside the Crew gateway.

The manifest names three functions in this file: ``register``, ``on_startup``
and ``on_shutdown``. Crew runs this file once per hook, so it keeps nothing of
its own; the service lives in ``service.py``.

Every route is for the dashboard owner only. Breaker shows what every session
spent and can stop work, so nobody else gets an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from aiohttp import web

from .breaker_core import ENFORCE, SHADOW, clean_amount, replay
from .runs import MAX_PROMPT_CHARS, RunRefused
from .service import VERSION, service_for, shut_down

MAX_SESSION_CHARS = 512
MAX_TITLE_CHARS = 80
MAX_NUDGE_CHARS = 2_000
MAX_CYCLES = 500
MIN_IDLE_SECS, MAX_IDLE_SECS = 30, 3_600


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    handler: Callable[..., Any]


# ---- hooks -----------------------------------------------------------------


def register(ctx: Any) -> list[Route]:
    """The routes Crew serves under ``/api/apps/breaker``."""
    return [
        Route("GET", "/state", get_state),
        Route("GET", "/history", get_history),
        Route("GET", "/replay", get_replay),
        Route("PUT", "/caps", put_cap),
        Route("POST", "/caps/remove", remove_cap),
        Route("POST", "/restart", post_restart),
        Route("POST", "/runs", post_run),
        Route("POST", "/runs/stop", stop_run),
        Route("POST", "/page-actions/{action_id}/done", page_action_done),
    ]


async def on_startup(ctx: Any) -> None:
    """Start the meter when the app is enabled or the gateway starts."""
    await service_for(ctx).start()


async def on_shutdown(ctx: Any) -> None:
    """Stop the meter and save, when the app is disabled or the gateway stops."""
    await shut_down()


# ---- helpers ---------------------------------------------------------------


def _ok(data: dict[str, Any] | None = None) -> web.Response:
    return web.json_response({"ok": True, **(data or {})})


def _refuse(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


async def _owner_only(request: Any, ctx: Any, operation: str) -> web.Response | None:
    """Crew's own refusal for anyone but the dashboard owner, or None for the owner."""
    gate = getattr(ctx, "require_owner", None)
    if not callable(gate):
        return _refuse("this Crew has no owner check, so Breaker answers nobody", 403)
    refusal: web.Response | None = await gate(request, operation)
    return refusal


async def _body(request: Any) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001 - a body that isn't JSON is an empty one
        return {}
    return data if isinstance(data, dict) else {}


def _session(body: dict[str, Any]) -> str:
    value = body.get("session")
    if isinstance(value, str) and 0 < len(value.strip()) <= MAX_SESSION_CHARS:
        return value.strip()
    return ""


def _whole(value: Any, low: int, high: int, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        return default
    return max(low, min(high, int(value)))


def _dashboard_state(request: Any) -> Any:
    """The dashboard state Crew's chat-slot handle asks each route to pass along."""
    try:
        return request.app["state"]
    except Exception:  # noqa: BLE001
        return None


async def _service(ctx: Any) -> Any:
    service = service_for(ctx)
    await service.start()
    return service


# ---- reading ---------------------------------------------------------------


async def get_state(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "state.read")) is not None:
        return refusal
    return web.json_response(await (await _service(ctx)).state())


async def get_history(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "history.read")) is not None:
        return refusal
    try:
        limit = int(request.query.get("limit", "100"))
    except ValueError:
        limit = 100
    return web.json_response({"events": await (await _service(ctx)).history(limit)})


async def get_replay(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "replay.read")) is not None:
        return refusal
    raw = request.query.get("limit", "")
    try:
        limit = clean_amount(float(raw)) if raw else None
    except ValueError:
        limit = None
    if raw and (limit is None or limit <= 0):
        return _refuse("limit must be a number above 0")
    return web.json_response(replay(limit) if limit else replay())


# ---- caps ------------------------------------------------------------------


async def put_cap(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "cap.set")) is not None:
        return refusal
    body = await _body(request)
    session = _session(body)
    if not session:
        return _refuse("session is required")
    limit = clean_amount(body.get("limit"))
    if limit is None:
        return _refuse("limit must be a number, 0 or more")
    mode = body.get("mode", SHADOW)
    if mode not in (SHADOW, ENFORCE):
        return _refuse('mode must be "shadow" or "enforce"')
    cap = await (await _service(ctx)).set_cap(session, limit, mode, body.get("warn_pct"))
    return _ok({"cap": cap})


async def remove_cap(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "cap.remove")) is not None:
        return refusal
    session = _session(await _body(request))
    if not session:
        return _refuse("session is required")
    await (await _service(ctx)).remove_cap(session)
    return _ok()


async def post_restart(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "cap.restart")) is not None:
        return refusal
    session = _session(await _body(request))
    if not session:
        return _refuse("session is required")
    result = await (await _service(ctx)).restart(session, _dashboard_state(request))
    return _ok(result)


# ---- runs under a breaker --------------------------------------------------


async def post_run(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "run.start")) is not None:
        return refusal
    body = await _body(request)
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return _refuse("prompt is required")
    if len(prompt) > MAX_PROMPT_CHARS:
        return _refuse(f"prompt is longer than {MAX_PROMPT_CHARS} characters")
    limit = clean_amount(body.get("limit"))
    if limit is None or limit <= 0:
        return _refuse("limit must be a number above 0: a run under a breaker needs a limit")
    title = body.get("title")
    title = title.strip()[:MAX_TITLE_CHARS] if isinstance(title, str) and title.strip() else ""
    nudge = body.get("nudge")
    nudge = nudge.strip()[:MAX_NUDGE_CHARS] if isinstance(nudge, str) else ""
    state = _dashboard_state(request)
    if state is None:
        return _refuse("this Crew gave the route no dashboard state, so no session can be opened", 503)
    try:
        record = await (await _service(ctx)).start_run(
            state,
            prompt=prompt.strip(),
            limit=limit,
            max_cycles=_whole(body.get("max_cycles"), 0, MAX_CYCLES, 10),
            idle_secs=_whole(body.get("idle_secs"), MIN_IDLE_SECS, MAX_IDLE_SECS, 60),
            title=title or f"Under a breaker: {prompt.strip()[:40]}",
            nudge=nudge,
        )
    except RunRefused as exc:
        return _refuse(str(exc), 409)
    return _ok({"session": record["session"], "loop_note": record.get("loop_note", "")})


async def stop_run(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "run.stop")) is not None:
        return refusal
    session = _session(await _body(request))
    if not session:
        return _refuse("session is required")
    stopped, note = await (await _service(ctx)).stop_run(session)
    return _ok({"note": note}) if stopped else _refuse(note, 409)


# ---- page actions ----------------------------------------------------------


async def page_action_done(request: Any, ctx: Any) -> web.Response:
    if (refusal := await _owner_only(request, ctx, "page_action.done")) is not None:
        return refusal
    body = await _body(request)
    action_id = str(request.match_info.get("action_id", ""))
    detail = body.get("detail")
    known = await (await _service(ctx)).page_action_done(
        action_id, body.get("ok") is True, detail[:300] if isinstance(detail, str) else ""
    )
    return _ok() if known else _refuse("no such page action", 404)


__all__ = ["VERSION", "Route", "on_shutdown", "on_startup", "register"]
