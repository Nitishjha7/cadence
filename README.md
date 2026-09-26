<div align="center">

# Cadence

**Sprint planning and capacity tool — dependency-aware task scheduling for small teams.**

</div>

> **Status: not deployed yet.** The dependency graph, capacity, sprint
> lifecycle, permissions, and all five screens are built and tested —
> `docker compose up`, run `seed_demo`, and log in to click through it.
> See [docs/PROJECT_WALKTHROUGH.md](docs/PROJECT_WALKTHROUGH.md) for how
> it's put together. This README will get real screenshots and a live URL
> once it's deployed.

---

## What this is not

It is not a Jira clone, and it is not a kanban board with drag-and-drop.

A board where you create a task, change its status and move a card is CRUD with a
nice front end. Cadence is built around the two questions that a board does not
answer:

**1. Can this task even be started?** Task B needs Task A finished first. A needs
the API keys. If someone accidentally makes the API keys task depend on B, three
tasks now wait on each other forever — and a board will happily let you do it and
show you nothing.

**2. Does the person it is assigned to have room?** Everyone has forty hours in a
sprint. Two of them are on leave. One already has fifty-two hours of work. A board
shows you cards; it does not show you that the sprint is over capacity before the
sprint starts.

Those two questions — a graph problem and an arithmetic problem — are the project.

---

## Overview

| | |
|---|---|
| **Backend** | Django 5, Python 3.12 |
| **Data** | PostgreSQL 16 |
| **Frontend** | Django templates + HTMX (server-rendered, no SPA) |
| **Async** | Celery + Celery Beat (overdue checks, daily digest) |
| **Admin** | Django admin as the manager console |
| **Infra** | Docker Compose |
| **Tests** | pytest, 65 passing |

---

## The three things worth reading the code for

### 1. Cycle detection before the write

```
A depends on B, B depends on C, C depends on A
```

Three tasks that can never start, and nothing on screen says so.

Cadence runs a depth-first search **before** the dependency is saved and rejects
the write with the actual cycle named:

```
Circular dependency:
  API keys  ->  Payment gateway  ->  API keys
Neither task could ever start.
```

The hard part is not detecting the obvious two-node case. It is detecting a cycle
five levels deep, while still allowing a **diamond** — `A->B`, `A->C`, `B->D`,
`C->D` — which looks like a cycle to a naive check and is perfectly legal.

### 2. Blocked status is derived, never set

No user ever sets a task to "blocked". A task is blocked if any dependency is
unfinished, and the moment the last one is completed it becomes available on its
own.

Stored status would drift the first time someone forgot to update it — and a
planning tool that lies about what is ready is worse than no tool.

### 3. Sprint scope is frozen at start

When a sprint starts, its committed scope is snapshotted. Work added afterwards is
recorded as **scope creep** and rendered separately on the burndown.

Without the snapshot, a team that adds work mid-sprint and finishes it looks
identical to a team that planned correctly — and the burndown quietly becomes
fiction.

---

## Documentation

| Doc | What is in it |
|---|---|
| [docs/PROJECT_WALKTHROUGH.md](docs/PROJECT_WALKTHROUGH.md) | How the app is put together — start here |
| [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) | Schema, cycle detection algorithm, capacity model, sprint snapshot |
| [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) | Build phases and what "done" means for each |
| [docs/TEST_PLAN.md](docs/TEST_PLAN.md) | Every test to write, grouped, with the graph cases spelled out |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | The four-minute walkthrough, screen by screen |
| [docs/UI_FLOW.md](docs/UI_FLOW.md) | The five screens, what each shows, and the seed data behind them |
| [docs/SETUP.md](docs/SETUP.md) | Getting it running locally |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Railway + Neon, why those, and what to verify after |
| [DECISIONS.md](DECISIONS.md) | A log of the non-obvious decisions and why I made them |

---

## Deliberate non-goals

Scope discipline is part of the design. These are **not** being built:

- **Drag-and-drop board** — looks impressive, teaches nothing, and costs days of
  front-end work that the dependency graph deserves instead.
- **Real-time collaborative updates** — a different problem (WebSockets, conflict
  resolution) already covered elsewhere in my portfolio.
- **Comments, attachments, custom fields, workflows** — breadth. The two questions
  in "What this is not" are depth.
- **Time tracking** — estimates are enough for capacity; actuals are a separate
  product.

---

## License

MIT
