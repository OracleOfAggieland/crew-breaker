# Breaker

**A circuit breaker for credits in Kiro Crew.** It trips at your limit, lets the running turn finish, and resets when you say. It gives a session a true total that includes its subagents, shows when a cap would have tripped, and holds a real cap wherever an app is allowed to hold one.

> **Status: design.** Nothing in this repo runs yet. This page says what Breaker is meant to do and what it won't be able to do. The real README replaces it as the build lands.

## Why

[Kiro Crew](https://github.com/kirodotdev/KiroCrew) can work for hours with nobody watching: goal loops, crons, Task Runner jobs, subagents. As of v0.13.1 it bounds that work by cycles and by time, not by credits.

- **The request:** [KiroCrew#6338](https://github.com/kirodotdev/KiroCrew/issues/6338) asks for a credit ceiling that pauses the work, tells the owner, and lets them resume. One report there describes a goal loop that carried a 5,000-credit budget in its own notes and spent about 31,000 in two and a half days, about 85% of it in subagents.
- **The design:** [KiroCrew#35488](https://github.com/kirodotdev/KiroCrew/pull/35488) is a request for change that works the fix out for Crew's core. First charge a subagent's credits to the session that spawned it, then stop an unattended loop at a turn boundary once that total passes a cap. The cap is off unless you set it. The design is its authors', and it is waiting on a maintainer's sign-off.

Breaker is that design tried out on the released version, as an opt-in app, using only what an app is allowed to use. It follows the design's choices and names where it can. Where an app can't do what core could, it says so and lists the missing seam.

## What it does

**1. A true session total.** Crew's stored usage rows don't say which session spawned a subagent, so session totals leave subagent spend out. Breaker records that link while a run is live and keeps it, so a session's total includes its children. It also reports how many runs it saw and how many it missed.

**2. A shadow cap.** Set `session_credits` on any session. Breaker evaluates the cap after every turn and stops nothing. It reports when the cap would have tripped, what was still running at that moment, and how far spend went past the cap before the work drained. Those are numbers the design's open questions ask for.

**3. A real cap, labelled by how well it holds.** Every capped session carries one of three labels:

| Label | Which work | How |
|---|---|---|
| **Enforced unattended** | Work you start from Breaker | Breaker owns the chat and its loop, so it checks the budget before each cycle starts. Task Runner jobs can also be paused unattended. |
| **Enforced while Breaker is open** | Loops you started yourself | Breaker's page acts with your authority and pauses the loop. When you arm the cap, Breaker also sets the loop's own cycle and runtime limits as a backstop for when the page is closed. |
| **Watch only** | Everything else | A note with the numbers and a link. |

**4. Replay.** The numbers from #6338, run through Breaker's real accounting. Counting only the session's own turns, the total ends near 4,650 and a 5,000 cap never trips. Counting its subagents, it trips at 5,000. That is the design's own argument for doing attribution first, made visible.

Rules it keeps, all taken from the design:

- **Drain, don't cut.** A turn or subagent that is already running finishes. No new cycle starts.
- **A tripped cap stays tripped** until the owner restarts the work. Raising the cap does not restart anything.
- **A message you type always runs.** Caps are for unattended work.
- **It fails open.** If Breaker can't read the meter, it warns and stops nothing.
- **Credits only.** A session on a backend that bills in dollars is marked "not enforced".

## What it can't do

- **Refuse a turn or a subagent before it starts** in a session it doesn't own. A finished subagent can wake its parent, and that turn can start new subagents with no loop cycle involved. Breaker can measure that gap; it can't close it.
- **See a top-level turn in flight.** Crew knows a turn's credits when the turn ends. Only running subagents report spend as they go, so a cap can be overshot by the turn in flight.
- **Charge a subagent it never saw running.** A run that starts and ends between two looks is counted but not tied to its parent.
- **Pause your own loop while Breaker is closed.** The routes that pause it need the owner, and an app's backend isn't the owner.
- **Put work back exactly as it was.** A resumed loop is a fresh run, and a cancelled subagent doesn't come back.

**Seams an app would need to do the rest:** usage rows stamped with the parent session, a way for the owner to let an app pause a named loop, and a point where an app can decline a turn or a spawn before it starts.

## How it's built

- **A pure core** in Python: the ledger that folds usage rows and live snapshots into a total per session, and the cap check. No I/O and no clock of its own.
- **Property-based tests** on that core, for the bounds the design states: a turn is never counted zero times, a finished prompt is never counted by both the ledger and the live figure, a tripped cap never restarts on its own, and unreadable meter data never stops anything.
- **A small backend** inside the Crew gateway that reads the meter, decides and records. It uses no private Crew internals. If a route or field it needs is missing, it drops to watch-only and says so.
- **A page** on the Crew app SDK.
- **Tested without spending credits,** on a stand-in backend that reports credits and on seeded usage rows.

## Install

Not yet.

## License

[MIT](LICENSE)
