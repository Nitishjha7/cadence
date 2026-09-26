# Project Walkthrough

How the app is put together, and why the non-obvious parts look the way
they do. [DECISIONS.md](../DECISIONS.md) has the terse log of individual
choices; this is the connected version.

---

## Layout

```
cadence/                   Django project package
├── settings.py             env-driven config, production hardening gated on DEBUG=0
├── celery.py                Celery app, wired to Django settings
└── urls.py                  admin, auth, and the three apps' urls.py included

projects/                  Who is working, on what, and who can do what
├── models.py                Project, Member
├── permissions.py            can_view/can_edit/can_manage — role checks
├── views_base.py              ProjectPermissionMixin — every view inherits this
├── views.py / urls.py         project list (the landing page)
├── management/commands/       seed_demo — builds a full demo project
└── admin.py

tasks/                     What needs doing, and the dependency graph
├── models.py                Task, TaskDependency
├── services.py               would_create_cycle() — the DFS cycle detector
├── views.py / urls.py         board, task detail, add-dependency (HTMX)
└── admin.py

sprints/                   Planning windows, capacity, burndown
├── models.py                Sprint (+ thin start()/add_task() wrappers), SprintCommitment,
│                             Capacity, TimeOff, WorkLog
├── services.py               capacity_for(), start_sprint(), scope_creep_tasks(),
│                             write_daily_worklogs(), velocity(), and friends
├── views.py / urls.py         capacity view, sprint detail + burndown
├── tasks.py                   Celery task: write_daily_worklogs_for_active_sprints
├── management/commands/       write_worklogs — run the nightly job by hand
└── admin.py

templates/                 Django templates + Tailwind (CDN) + HTMX (CDN)
├── base.html                 nav, messages, htmx/tailwind script tags
├── registration/login.html
└── projects/, tasks/, sprints/  one template per screen, one HTMX partial
                                 (tasks/_dependencies.html) swapped in place

tests/
├── factories.py             factory_boy factories for every model
├── test_dependency_graph.py  cycle detection
├── test_blocking.py          derived is_blocked
├── test_capacity.py          capacity arithmetic, time off, allocation
├── test_sprints.py           start_sprint atomicity, scope creep, burndown, velocity
├── test_permissions.py       role checks, HTTP 404-not-403, a URLconf mixin walk
└── test_queries.py           board/capacity run in a constant number of queries

.github/workflows/ci.yml    ruff + pytest against real postgres/redis, on push and PR
docker-compose.yml          postgres, redis, web, worker, beat — 5 services
Dockerfile                  python:3.12-slim
```

`docker compose up` brings up all five services; `migrate` runs clean;
`seed_demo` builds the full demo project; the Django admin lists every
model and is reachable only by the manager login.

---

## The dependency graph

The rule: a `TaskDependency` can only be created if it doesn't close a
loop. [tasks/services.py](../tasks/services.py)'s `would_create_cycle`
walks forward from the task being depended on, and if the walk reaches the
task doing the depending, the new edge would close a cycle. It's an
iterative DFS rather than recursive, so a long chain can't blow a
recursion limit, and it tracks the path it took so a rejection can report
the actual loop — `CAD-3 -> CAD-7 -> CAD-3` — instead of just refusing.

The one line that matters most is the `seen` set. `A->B`, `A->C`, `B->D`,
`C->D` is a legal diamond, not a cycle — the walk reaches `D` twice, once
through `B` and once through `C`, and without tracking visited nodes the
second arrival looks like a revisit. Getting a diamond wrong is the most
likely bug in a check like this, which is why `test_diamond_is_allowed`
exists specifically to catch it, alongside a test that builds 200 random
edges against a 30-node graph and checks the result with a second,
independently-written cycle checker rather than the same function under
test.

`TaskDependency.clean()` is the only place this rule lives — three lines
that call `would_create_cycle` and raise `ValidationError` with the path if
it returns one. Because Django calls `clean()` on `full_clean()`, the same
check runs whether the dependency comes from the admin, a form, or the
HTMX add-dependency view; there's no second code path that could forget
to re-check it.

## Derived status, not stored status

`Task.is_blocked` ([tasks/models.py](../tasks/models.py)) is a property —
`any dependency not done` — not a database column. Nothing sets it and
nothing signals on it. Completing a task's last dependency doesn't touch
that task's own row at all; the next read of `is_blocked` just computes a
different answer. A stored flag would need updating every time a
dependency's state changed, and the first missed update would leave a task
saying "blocked" when it's actually ready, or the reverse — which is worse
than not tracking it at all.

The same pattern shows up again in sprints: scope creep isn't a flag
either. A task in an active sprint with no matching `SprintCommitment` row
was added after the sprint started — that absence is the entire
definition, checked with `sprint.tasks.exclude(commitments__sprint=sprint)`.

## Capacity

[sprints/services.py](../sprints/services.py) computes
`available_hours = weekly_hours * (sprint_days / 7) - timeoff_hours`. The
part worth reading closely is how time off is counted: a leave range gets
clipped to the sprint window first, then only the weekdays inside that
clipped range count as lost capacity — a weekend inside someone's leave was
never sprint capacity to begin with, so it doesn't get subtracted.

Over-allocation is a boolean a caller checks, not a save-time rejection.
Nothing in the codebase stops a task from being assigned to someone already
over capacity — managers legitimately do this on purpose (a deadline, a
specialist nobody else can cover), and a tool that refused would just get
worked around.

## Sprint lifecycle

`start_sprint()` is the one place using `@transaction.atomic`: it writes a
`SprintCommitment` row (copying the current estimate) for every task in the
sprint, computes and stores a `Capacity` row for every project member, and
stamps `started_at` — all three happen together or none of them do. Both
snapshots are taken at start rather than computed later, because both
inputs drift afterwards: estimates get revised, leave gets booked. Calling
`start()` on a sprint that isn't `planned` raises rather than silently
re-snapshotting, since re-running it would let a live sprint's committed
numbers quietly move.

`committed_hours()` and `added_hours()` stay as two separate sums instead
of one number with a footnote — committed reads the frozen
`estimate_hours_at_start` off `SprintCommitment` rows, added reads the
current estimate off whatever scope creep exists. Keeping them separate all
the way to the template is what makes the burndown's step-up on the day
scope was added visible instead of just flattening the line.

`write_daily_worklogs()` snapshots each unfinished task's remaining hours
into one `WorkLog` row per day, keyed on `(task, date)`. It runs nightly
through a Celery beat schedule (`sprints/tasks.py`), and the same logic is
exposed as a management command (`write_worklogs`) for running it by hand.
Reconstructing burndown history from today's estimates wouldn't work once
those estimates change — the daily row is the only honest source.

`velocity()` averages committed hours — never added hours — across the
most recent completed sprints, and returns `None` until at least three
exist. Counting scope creep here would let a chaotic sprint look fast and
inflate the next sprint's plan.

## Permissions

Three roles — viewer, contributor, manager — checked by
[projects/permissions.py](../projects/permissions.py)'s three functions
against a user's `Member.role` in a project.
[projects/views_base.py](../projects/views_base.py)'s
`ProjectPermissionMixin` resolves the project from the URL and every
project-scoped view inherits it, so permission checks live in one place
rather than being repeated per view. A user who isn't a member of a
project gets a 404, not a 403 — a 403 would itself confirm the project
exists, which a non-member shouldn't get for free.

## The five screens

Board and task detail are read-only views over the graph above. The
add-dependency interaction is HTMX: submitting the form hits the same
`TaskDependency.clean()` the admin and API would hit, and a rejected
`ValidationError` renders as the on-page cycle box with no separate error
path to keep in sync. State changes are enforced server-side — a blocked
task can't move to in-progress or done regardless of what the UI shows,
since a disabled `<select>` is a hint, not a guarantee. The burndown is
drawn as plain CSS bars, one `<div>` per day with height set by
`{% widthratio %}` — no charting library, since the data itself is the
point, not the rendering.

Two query-count bugs came up while building the board and capacity views
and are worth naming because they're the kind of thing that ships silently
otherwise: `is_blocked`'s query didn't respect `prefetch_related` on its
own — a property has to be taught to check the prefetch cache before
falling back to a live query, prefetching alone doesn't do that for you —
and a missing `project` in `select_related` meant `task.key` lazy-loaded it
once per task. Both are fixed and pinned by
[tests/test_queries.py](../tests/test_queries.py), which asserts the board
and capacity views run in a constant number of queries regardless of how
many tasks or members exist.

## The demo data

`seed_demo` builds one project with roughly fifty tasks, six members
across all three roles, and three sprints — two completed (for velocity)
and one active. It's deliberately not a minimal fixture: it includes a
dependency chain several levels deep, a real diamond in the graph, two
members genuinely over capacity, one on leave mid-sprint, a few
unestimated tasks, and scope creep added partway through the active
sprint with daily worklogs on both sides of it. The cycle-rejection demo
(add a dependency between two specific tasks and watch it get rejected)
is pinned to a fixed pair of task numbers so it reproduces the same way
every time the seeder runs.

---

## Running it

```bash
cp .env.example .env
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
docker compose exec web pytest -v
```

Then open `http://localhost:8005/` and log in (see [SETUP.md](SETUP.md)
for the three demo logins). From the board, open the API keys task and try
adding a dependency on the payment gateway task — it rejects with the
actual cycle path, live, no shell required.

---

## What's left

The application and its tests are done. Deployment (Railway + Neon) is the
remaining piece — see [DEPLOYMENT.md](DEPLOYMENT.md) for the exact steps.
