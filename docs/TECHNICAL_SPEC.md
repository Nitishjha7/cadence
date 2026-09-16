# Technical Specification

Schema, algorithms and the decisions behind them. Build order is in
[BUILD_PLAN.md](BUILD_PLAN.md); the tests that pin this behaviour are in
[TEST_PLAN.md](TEST_PLAN.md).

---

## Contents

1. [Schema](#1-schema)
2. [The dependency graph](#2-the-dependency-graph)
3. [Derived status](#3-derived-status)
4. [Capacity](#4-capacity)
5. [Sprints and scope](#5-sprints-and-scope)
6. [Permissions](#6-permissions)
7. [Time and testability](#7-time-and-testability)

---

## 1. Schema

Nine models. UUID primary keys.

### `Project`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `name`, `key` | char | `key` is the task prefix — `CAD-14` |
| `created_at` | datetime | |

### `Member`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `user` | FK to `auth.User` | Django auth is used as-is, not replaced |
| `project` | FK | |
| `role` | choice | `manager`, `contributor`, `viewer` |
| `weekly_hours` | int | Default 40 — the baseline for capacity |

### `Task`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `project` | FK | |
| `number` | int | Sequential per project — `CAD-14` |
| `title`, `description` | text | |
| `state` | choice | `todo`, `in_progress`, `done` |
| `assignee` | FK to Member, null | |
| `estimate_hours` | decimal | Null means unestimated, which capacity must handle |
| `sprint` | FK, null | |
| `created_at` | datetime | |

> `state` holds only three values, and **`blocked` is not one of them.** Blocked is
> computed — see §3.

### `TaskDependency`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `task` | FK | The task that waits |
| `depends_on` | FK | The task that must finish first |

Constraints:
- `UNIQUE (task, depends_on)` — the same edge cannot be added twice
- `CHECK (task_id != depends_on_id)` — a task cannot depend on itself
- Cycle rejection happens in `clean()`, before save — see §2

The self-dependency check is a database constraint rather than only application
logic, because it is the one cycle case that is cheap to enforce there.

### `Sprint`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `project` | FK | |
| `name` | char | "Sprint 12" |
| `starts_on`, `ends_on` | date | |
| `state` | choice | `planned`, `active`, `completed` |
| `started_at` | datetime, null | When the snapshot was taken |

### `SprintCommitment`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `sprint` | FK | |
| `task` | FK | |
| `estimate_hours_at_start` | decimal | Frozen at sprint start |

Written once, when the sprint starts. This is the snapshot that makes scope creep
visible — see §5. The estimate is copied, not referenced, because re-estimating a
task mid-sprint must not retroactively change what was committed.

### `Capacity`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `member` | FK | |
| `sprint` | FK | |
| `available_hours` | decimal | Computed at sprint start, stored |

### `TimeOff`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `member` | FK | |
| `starts_on`, `ends_on` | date | Inclusive |
| `reason` | char | |

### `WorkLog`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `task` | FK | |
| `date` | date | |
| `remaining_hours` | decimal | Snapshot of what is left |

One row per task per day, written by a nightly Celery task. This is what the
burndown is drawn from — reconstructing history from the current state is not
possible once estimates change.

---

## 2. The dependency graph

### The rule

A dependency may be created only if it does not introduce a cycle.

### The algorithm

Before saving `TaskDependency(task=X, depends_on=Y)`, ask: **is X already
reachable from Y?** If yes, adding the edge closes a loop.

```python
def would_create_cycle(task, depends_on):
    # Walk forward from depends_on. If we reach task, the edge closes a cycle.
    seen = set()
    stack = [depends_on]
    while stack:
        current = stack.pop()
        if current == task:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(dependencies_of(current))
    return False
```

Iterative rather than recursive — a deep chain would otherwise risk a recursion
limit, and the iterative form is no harder to read.

`seen` is what makes a **diamond** legal. In `A->B`, `A->C`, `B->D`, `C->D`, the
walk reaches D by two routes; without `seen` the second visit looks like a
revisit and a naive implementation calls it a cycle. **Rejecting a legal diamond
is the most likely bug in this file**, and [TEST_PLAN.md](TEST_PLAN.md) §1 pins it.

### Where it runs

In `TaskDependency.clean()`, so it applies to the admin, forms, and the API alike.
Putting it only in a view leaves the admin able to create a cycle — and the admin
is the manager console.

### Error message

The error names the actual path, not just the fact:

```
Circular dependency:
  CAD-3 (API keys) -> CAD-7 (Payment gateway) -> CAD-3 (API keys)
Neither task could ever start.
```

The path is a by-product of the DFS — recording the route when the target is
reached costs nothing and turns an error into an explanation.

### Scale

Graphs here are hundreds of nodes, not millions. The walk is O(V+E) per insert and
runs in microseconds. A transitive-closure table would make reads faster and every
write more complicated; it is not warranted at this size, and that trade-off is
the answer to "how would this scale?" rather than something to pre-build.

---

## 3. Derived status

**A task is blocked if any of its dependencies is not `done`.**

```python
@property
def is_blocked(self):
    return self.dependencies.exclude(depends_on__state="done").exists()
```

Not stored. Not set by a user. Not updated by a signal.

**Why not store it.** A stored flag needs updating whenever any dependency
changes state, and the first missed update produces a task that says "blocked"
when it is ready, or worse, "ready" when it is not. A planning tool that lies
about readiness is worse than no tool.

**The cost.** A board rendering 45 tasks would issue a query per task.
`prefetch_related('dependencies__depends_on')` reduces it to two queries total,
and [TEST_PLAN.md](TEST_PLAN.md) §4 has a test asserting the query count so the
N+1 cannot creep back in.

Completing a task therefore unblocks its dependents with no write of any kind —
the next read simply computes a different answer.

---

## 4. Capacity

### The calculation

```
available_hours = weekly_hours * (sprint_days / 7) - timeoff_hours
```

`timeoff_hours` counts only **working days** of leave that fall inside the sprint
window. A weekend inside a leave range is not capacity that was lost, because it
was never capacity.

### Allocation

```
allocated_hours = sum(estimate_hours for assigned, unfinished tasks in the sprint)
```

Unestimated tasks count as **zero**, and the UI shows the count separately:

```
Rahul    31 / 40 hrs     (2 tasks unestimated)
```

Treating unknown as zero silently understates load; treating it as some default
invents data. Showing it is the honest option, and it is a deliberate one.

### Over-allocation warns, it does not block

A member over capacity is flagged, not prevented from being assigned more.

> Managers legitimately overload people — a deadline, a specialist nobody else can
> replace, a week where it is simply accepted. A tool that refuses would be worked
> around within a day, and then it would know nothing.

The same reasoning applies at sprint level: 200 hours of work against 150 hours of
team capacity is a warning at the top of the sprint page, not a rejected save.

---

## 5. Sprints and scope

### Starting a sprint

Transition `planned -> active` does three things, in one transaction:

1. Writes a `SprintCommitment` row for every task in the sprint, **copying the
   current estimate**.
2. Computes and stores `Capacity` for every member.
3. Stamps `started_at`.

Both snapshots are taken **at start** rather than computed later, because both
inputs change during a sprint. Estimates get revised; leave gets booked. A
burndown computed from today's numbers would show a sprint that was never planned.

### Scope creep

A task in an active sprint with **no `SprintCommitment` row** was added after the
start. That is the whole definition — no extra flag needed.

The burndown renders committed and added work in separate series, so a mid-sprint
addition appears as a visible step up rather than silently flattening the line.

### Burndown

Drawn from `WorkLog`, one row per task per day, written nightly by Celery.

Reconstructing history from current state is impossible once estimates change —
the daily snapshot is the only honest source. Cheap: a few hundred rows per
sprint.

### Velocity

Completed committed hours from the last three completed sprints. Committed only —
counting scope creep in velocity would let a chaotic sprint look fast and then
inflate the next sprint's plan.

---

## 6. Permissions

Three roles, enforced with Django's permission system rather than `if` statements
in views.

| Role | Can |
|---|---|
| `viewer` | Read everything in their projects |
| `contributor` | Create and edit tasks, change state, add dependencies |
| `manager` | All of the above, plus start/complete sprints and manage members |

Object-level checks live in a mixin used by every view, so a new view cannot
silently be unprotected. Django admin remains manager-only and acts as the
back-office console — which is a large part of why this project is in Django at
all.

---

## 7. Time and testability

Nothing calls `timezone.now()` inside business logic. Dates are parameters, or
come from an injected clock.

Tests use `freezegun` to move through a sprint in milliseconds:

```python
with freeze_time("2026-09-01"):
    sprint.start()

with freeze_time("2026-09-08"):
    complete_task(task_a)
    write_daily_worklogs()
```

A fourteen-day sprint with a daily burndown is otherwise untestable without
waiting fourteen days.
