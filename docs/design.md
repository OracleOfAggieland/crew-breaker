# Breaker: design

Breaker is a Kiro Crew app. It targets Crew v0.13.1 and uses only what that release lets a third-party app use.

## Parts

```
app.json                  the manifest
backend/
  breaker_core/           the accounting and the cap: pure Python, no I/O
  routes.py               the app's HTTP routes, served inside the gateway
  service.py              the one running Breaker: reads, decides, stops, saves
  meter.py                reads Crew's usage log, the running subagents and the goal loops
  runs.py                 work Breaker starts and owns
ui/
  src/                    the page (React, on the Crew app SDK)
  dist/index.mjs          the built page, committed
dev/                      a stand-in model backend that reports credits, and the icon's generator
tests/                    pytest and Hypothesis
```

## The core (`backend/breaker_core`)

- **`Ledger`** folds two kinds of facts into a spend total per session:
  - a `TurnRow`, one settled row of Crew's usage log (`usage/tokens/YYYY-MM-DD.jsonl` under the data home);
  - a `Snapshot`, the subagent runs running right now, each with its parent session and the credits it has billed so far.
- A run contributes `max(settled rows, highest live figure)`, so a credit is counted once.
- The first parent link learned for a run stands, and a link that would make a loop is refused.
- **`Cap`** is a limit on a session and the subagents under it: `armed`, then `warned` once at `warn_pct`, then `tripped`. A trip stays until `restart`. After a trip the cap keeps measuring until nothing under the session is running, and records the overshoot.
- **`Breaker`** ties one ledger to its caps and keeps a history. `to_json` and `from_json` save and restore it.
- **`replay`** runs the totals reported on KiroCrew#6338 through the same code.

The core never stops anything. `stops_for(signal, mode, label)` says what the caller should do.

## How well a cap holds

Every capped session has a label:

| Label | Meaning | How Breaker stops the work |
|---|---|---|
| `unattended` | Breaker started the work and owns its chat slot | Through the app's own chat-slot handle: the loop is not armed again and no new cycle starts |
| `while_open` | The owner started a goal loop on the session | The page, which acts with the owner's authority, pauses the loop. The backend queues the action and the page carries it out |
| `watch` | Anything else | Breaker records the trip and tells the owner |

A cap in `shadow` mode is evaluated the same way and stops nothing.

## Rules

- A turn or subagent that is already running is never cut.
- A tripped cap stays tripped until the owner restarts. Raising the limit restarts nothing.
- A message the owner types is never refused.
- Unreadable meter data stops nothing. The page shows the meter as unreadable.
- Credits only. A session that has billed dollars and no credits is marked as not enforced.
- No private Crew internals: no `kiro_crew` imports, no reaching through `ctx.http_app`. The dashboard state is touched only to hand it to the chat-slot handle, which asks for it. If a route, a field or a `ctx` handle is missing, that feature is off and the page says so.
- Every route is for the owner only (`ctx.require_owner`).
- Breaker writes only to its own data folder.

## The backend's HTTP routes

All under `/api/apps/breaker`. Bodies and answers are JSON.

### `GET /state`

```json
{
  "version": "0.1.0",
  "now": "2026-11-24T08:00:00+00:00",
  "usage_log": "the folder of usage files being read",
  "meter": {"ok": true, "note": "", "last_read": "2026-11-24T07:59:50+00:00", "live_ok": true, "live_note": ""},
  "capabilities": {"chat_slots": true, "live_runs": true, "loops": true},
  "sessions": [
    {
      "session": "slot key",
      "title": "",
      "own": 120.5, "children": 410.0, "total": 530.5, "dollars": 0.0,
      "runs": 3, "running": ["run session key"],
      "surface": "dashboard", "app": "", "last_spend": "2026-11-24T07:46:09+00:00",
      "orphan_run": false, "bills_in_dollars": false,
      "owned": false,
      "label": "while_open",
      "loop": {"id": "loop id", "active": true, "cycle_count": 4, "max_cycles": 50},
      "run": null,
      "cap": {
        "session": "slot key", "limit": 500, "mode": "enforce", "warn_pct": 80,
        "state": "tripped",
        "trip": {"seq": 91, "total": 512.0, "limit": 500, "running": ["run session key"], "peak": 530.5, "drained_seq": null, "overshoot": 30.5},
        "past_trips": []
      }
    }
  ],
  "coverage": {"linked_runs": 3, "linked_credits": 410.0, "orphan_runs": 0, "orphan_credits": 0.0, "rows_folded": 40, "rows_refused": 0},
  "grand_total": 530.5,
  "page_actions": [
    {"id": "a1", "kind": "pause_loop", "session": "slot key", "loop_id": "loop id", "reason": "credit_cap"}
  ]
}
```

- `loop`, `run` and `cap` are `null` when there is none. `run` is set on work Breaker started: `{"session", "title", "max_cycles", "idle_secs", "nudge", "loop_id", "loop_note", "cycles_done", "stopped"}`. `sessions` is every session Breaker has seen spend on, newest spend first.
- `page_actions` are stops that need the owner's authority. The page carries each one out and reports back.

### Caps

| Route | Body | Answer |
|---|---|---|
| `PUT /caps` | `{"session", "limit", "mode": "shadow" or "enforce", "warn_pct"}` | `{"ok": true, "cap": {...}}` |
| `POST /caps/remove` | `{"session"}` | `{"ok": true}` |
| `POST /restart` | `{"session"}` | `{"ok": true, "signals": ["tripped"], "note": ""}` |

`limit` must be a number; text that looks like a number is refused. A restart on work Breaker started arms its loop again for the cycles that were left. A restart while the total is still past the limit trips again at once, so raise the limit first.

### Page actions

`POST /page-actions/{id}/done` with `{"ok": true or false, "detail": ""}` answers `{"ok": true}`. An action nobody carries out stays in `page_actions`.

### History

`GET /history?limit=100` answers `{"events": [{"seq", "at", "kind", "session", "total", "limit", "overshoot", "mode", "detail"}]}`, newest first. `kind` is one of `cap_set`, `cap_removed`, `warned`, `tripped`, `drained`, `restarted`, `run_started`, `stopped`, `stop_failed`, `page_action_queued`.

### Replay

`GET /replay?limit=5000` answers what `breaker_core.replay.replay(limit)` returns: `source`, `limit`, `cycles`, `steps` (each with `cycle`, `what`, `session_only`, `with_subagents`, `capped`, `signals`) and `summary`.

### Runs under a breaker

| Route | Body | Answer |
|---|---|---|
| `POST /runs` | `{"prompt", "limit", "title", "max_cycles", "idle_secs", "nudge"}` | `{"ok": true, "session": "slot key", "loop_note": ""}` |
| `POST /runs/stop` | `{"session"}` | `{"ok": true, "note": ""}`, or 409 when there was no loop to stop |

A run is a chat slot Breaker owns (`breaker-<id>`), with a cap in `enforce` mode and a goal loop Breaker armed through its chat-slot handle. When the cap trips, Breaker removes that loop with the stop reason `credit_cap`, so no further cycle starts. If a loop shows up on a tripped run again, it is removed again.

Errors answer with a 4xx status and `{"ok": false, "error": "what was wrong"}`.

## The meter

- **Settled spend:** the backend reads the usage log files directly, remembering how far it got in each. Only whole lines are read. Crew's own `pipeline-conductor` skill reads the same files the same way.
- **Running subagents:** `GET /api/sessions/memory` with the app's token, every 10 seconds. It lists only runs that are running, and a subagent's usage row names no parent, so the link has to be caught while the run is alive. A run that starts and ends between two looks is counted but not tied to a parent.
- **Goal loops:** `GET /api/autonudge` with the app's token.
- If the usage log can't be read, `meter.ok` is false and nothing trips. If the running-subagent route can't be read, `meter.live_ok` is false and totals fall back to settled rows.

## Testing without credits

Crew's bundled fake backend reports no credits. `dev/credit_backend.py` wraps it and reports them the way kiro-cli does, so a development gateway writes real usage rows and every path can be exercised for nothing. A prompt can set what its turn bills (`credits=40`) and how long it runs (`sleep=30`).
