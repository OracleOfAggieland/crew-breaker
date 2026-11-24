# Fuse

**A credit fuse for Kiro Crew.** Put a budget on a session, a goal loop, a cron job or a whole day of background work. When spend crosses it, the fuse blows: the work pauses, you get a note saying what was stopped, and nothing starts again until you re-arm it.

> **Status: design.** Nothing in this repo runs yet. This page says what Fuse is meant to do and what it won't be able to do. The real README replaces it as the build lands.

## Why

[Kiro Crew](https://github.com/kirodotdev/KiroCrew) can work for hours with nobody watching: goal loops, crons, Task Runner jobs, subagents. As of v0.13.1 it bounds that work by time and by cycle count, not by credits.

The open request for a credit ceiling is [KiroCrew#6338](https://github.com/kirodotdev/KiroCrew/issues/6338). It asks for a cap per session, per time window and per cron job that pauses the work, tells the owner, and lets them raise the cap or resume. One report on that issue describes a goal loop that carried a 5,000-credit budget in its own notes and spent about 31,000 in two and a half days, about 85% of it in subagents, because nothing was reading the meter.

A cap inside Crew changes behaviour for everyone. An app is opt-in, so it can be strict for the people who want that and change nothing for those who don't.

There are already apps that chart spend. Fuse is for the step after the chart: stopping.

## What it does

| | |
|---|---|
| **Fuses** | A credit limit on one session, one goal loop, one cron job, or all background work in a day. Each has a warning mark, 80% by default. |
| **A live meter** | Spend per session as it happens, with subagent spend counted against the session that spawned it. |
| **Drain, don't kill** | At the limit, the turn that is running finishes. What would start the next one is paused: the loop, the cron, the Task Runner job, the subagents. Interrupting the turn itself is an option on each fuse. |
| **A note** | What blew, what it spent, what was paused, and how to re-arm. |
| **Re-arm** | Raising the limit or resetting the fuse restores exactly what Fuse paused, and nothing else. |
| **A ledger** | Every warning, stop and re-arm, with the numbers behind it. |

Rules it keeps:

- **A blown fuse stays blown** until the owner re-arms it. A restart doesn't reset it.
- **It fails open.** If Fuse can't read the meter, it warns and stops nothing.
- **It never refuses a message you type yourself.** Fuses are for unattended work.
- **It pauses only what it can restore.**

## What it won't do

- **It can't refuse a turn before it starts.** Crew gives apps no admission hook, so Fuse acts between turns, and a fuse can be overshot by the turn in flight.
- **Credits are a Kiro CLI number.** Other harnesses report cost in dollars. Fuse will meter those in dollars or not at all, and say which.
- **Some stops need the owner's authority.** Each fuse will say whether Fuse can stop that work unattended or only while its page is open.
- **It doesn't edit Crew's own files or database.**

## How it's built

- **A pure core** in Python: the accounting (usage rows and live snapshots folded into spend per fuse, each credit counted once), the fuse state machine, and the planner that turns a blown fuse into the smallest set of stops. No I/O and no clock of its own.
- **Property-based tests** on that core: spend never goes down, a credit is never counted twice, a blown fuse never re-arms itself, bad meter data never produces a stop, and re-arm restores exactly what was paused.
- **A small backend** inside the Crew gateway that polls, decides and records.
- **A page** on the Crew app SDK, with a control in the chat composer to set a budget for the chat you're in.

## Install

Not yet.

## License

[MIT](LICENSE)
