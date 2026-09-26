# Architecture

How Cadence is put together, and why the awkward parts are the way they are.

## The idea

A board where you create a task, move it across columns, and change its
status is CRUD with a nice front end. It doesn't answer the two questions
that actually decide whether a sprint goes well: can this task even be
started, and does the person it's assigned to have room? Those are a graph
problem and an arithmetic problem, and they're the whole project.

## Schema

Nine models, UUID primary keys, across three Django apps.

| Model | App | Notes |
|---|---|---|
| `Project` | projects | `key` is the task prefix — `CAD-14` |
| `Member` | projects | A user's role (manager/contributor/viewer) and weekly hours, per project |
| `Task` | tasks | `state` holds only `todo`/`in_progress`/`done` — **`blocked` is not one of them**, it's derived |
| `TaskDependency` | tasks | The edge of the dependency graph |
| `Sprint` | sprints | `planned` → `active` → `completed` |
| `SprintCommitment` | sprints | Frozen estimate per task, written once at sprint start |
| `Capacity` | sprints | Frozen available hours per member, written once at sprint start |
| `TimeOff` | sprints | A member's leave range |
| `WorkLog` | sprints | One row per task per day — what the burndown is drawn from |

`TaskDependency` carries a `UNIQUE (task, depends_on)` constraint and a
`CHECK (task_id != depends_on_id)` — the self-dependency case is cheap
enough to enforce at the database level directly, rather than relying only
on application logic.

## The dependency graph

Before saving `TaskDependency(task=X, depends_on=Y)`: is X already
reachable from Y? If yes, adding the edge closes a loop.

```python
def would_create_cycle(task, depends_on):
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

Iterative rather than recursive, since a deep chain would otherwise risk a
recursion limit — the iterative form isn't harder to read.

`seen` is what makes a **diamond** legal. In `A->B`, `A->C`, `B->D`,
`C->D`, the walk reaches D by two routes; without `seen` the second visit
looks like a revisit and a naive implementation calls it a cycle.
Rejecting a legal diamond is the most likely bug in this function, which
is why it has its own dedicated test, alongside an invariant test that
builds 200 random edges and checks the result with a second,
independently-written cycle checker — asserting with the same function
under test would only prove it agrees with itself.

This runs inside `TaskDependency.clean()`, not in a view, so it applies
to the admin, forms, and the HTMX add-dependency endpoint alike. Putting
it only in a view would leave the admin able to create a cycle — and the
admin is the manager console.

The error names the actual path, since the path is a by-product of the
walk anyway:

```
Circular dependency:
  CAD-3 (API keys) -> CAD-7 (Payment gateway) -> CAD-3 (API keys)
Neither task could ever start.
```

**Scale.** Graphs here are hundreds of nodes, not millions — the walk is
O(V+E) per insert, microseconds in practice. A transitive-closure table
would make reads faster and every write more complicated; not warranted
at this size, and that trade-off is the honest answer to "how would this
scale?" rather than something to pre-build.

## Derived status

A task is blocked if any of its dependencies isn't `done`:

```python
@property
def is_blocked(self):
    return self.dependencies.exclude(depends_on__state="done").exists()
```

Not stored, not set by a user, not updated by a signal. A stored flag
would need updating whenever any dependency changes state, and the first
missed update produces a task that says "blocked" when it's ready, or
"ready" when it's not — a planning tool that lies about readiness is
worse than no tool. Completing a task's last dependency unblocks it with
no write of any kind; the next read simply computes a different answer.

The cost is an N+1: a board rendering 45 tasks would otherwise issue a
query per task. `prefetch_related('dependencies__depends_on')` reduces
that to a constant, and a query-count test pins it so the N+1 can't creep
back in silently — see [testing.md](testing.md).

## Capacity

```
available_hours = weekly_hours * (sprint_days / 7) - timeoff_hours
allocated_hours = sum(estimate_hours for assigned, unfinished tasks)
```

`timeoff_hours` counts only working days of leave inside the sprint
window — a weekend inside a leave range was never capacity, so it doesn't
get subtracted. Unestimated tasks count as zero and are reported
separately in the UI (`2 tasks unestimated`); treating unknown as zero
silently understates load, and inventing a default invents data.

Over-allocation warns, it doesn't block. Managers legitimately overload
people on purpose — a deadline, a specialist nobody else can cover — and a
tool that refuses gets worked around within a day and then knows nothing.

## Sprints and scope

Starting a sprint (`planned` → `active`) does three things in one
transaction: writes a `SprintCommitment` row for every task, copying its
current estimate; computes and stores `Capacity` for every member; stamps
`started_at`. Both snapshots are taken at start rather than computed
later, because both inputs drift afterwards — estimates get revised,
leave gets booked. A burndown computed from today's numbers would show a
sprint that was never planned.

A task in an active sprint with **no matching commitment row** was added
after the start — that absence is the entire definition of scope creep,
no separate flag needed. The burndown renders committed and added work as
two separate series, so a mid-sprint addition shows up as a visible step
rather than silently flattening the line.

`WorkLog` is one row per task per day, written nightly by Celery beat.
Reconstructing burndown history from current estimates is impossible once
those estimates change — the daily snapshot is the only honest source.

Velocity averages committed hours (never added hours) across the last
three completed sprints, and returns nothing until three exist — counting
scope creep here would let a chaotic sprint look fast and inflate the
next sprint's plan.

## Permissions

Three roles — viewer, contributor, manager — checked against a `Member`
row's role in a project. A permission mixin resolves the project from the
URL and every project-scoped view inherits it, so the check lives in one
place rather than being repeated per view. A user who isn't a member of a
project gets a **404, not a 403** — a 403 would itself confirm the
project exists, which a non-member shouldn't get for free. Django admin
is manager-only and acts as the back-office console.

## The five screens

Django templates, server-rendered, no SPA — HTMX handles the two places
that need a partial update: the inline add-dependency form and the task
state selector.

| Screen | Route | Shows |
|---|---|---|
| Board | `/projects/{id}/board/` | Tasks by state; blocked ones greyed, with what blocks them named |
| Task detail | `/tasks/{id}/` | Dependencies in both directions |
| Add dependency | inline, HTMX | The cycle-rejection box, naming the actual path |
| Capacity | `/sprints/{id}/capacity/` | Load bars, leave, over-allocation |
| Sprint + burndown | `/sprints/{id}/` | Scope creep, visibly, as a separate series |

The add-dependency interaction hits the same `TaskDependency.clean()` the
admin and API would hit — a rejected `ValidationError` renders as the
on-page cycle box with no separate error path to keep in sync. State
changes are enforced server-side; a disabled `<select>` in the template
is a hint, not the guarantee.

## Known limits

- The graph walk runs on every dependency insert — fine at a few hundred
  tasks, not at a hundred thousand. A transitive-closure table is the
  alternative, and wasn't built because it couldn't be honestly tested at
  a scale where it matters.
- Capacity assumes uniform working days (8h/day, weekends off) — no
  partial days, no holiday calendar.
- Dependency writes aren't serialized. Two people adding dependencies to
  the same graph at once could each pass a check the other invalidates;
  the window is tiny and the failure is recoverable (delete the bad
  edge). A real fix would take a row lock on the project.
- Not deployed yet — the Compose stack is production-shaped, nothing is
  hosted.
