# Project Walkthrough

A running account of what actually got built, in the order it got built, and
why each piece looks the way it does. [DECISIONS.md](../DECISIONS.md) is the
terse log of individual choices; this is the connected story — read this
first, then dip into DECISIONS.md for the reasoning behind any one line.

Status as of this writing: **Phases 1-5 are done** — foundation, the
dependency graph, capacity, sprint start/snapshot/burndown/velocity, and
now the UI: permissions, all five screens, and `seed_demo`. Only
deployment (Phase 6) is left — see [BUILD_PLAN.md](BUILD_PLAN.md) and
[DEPLOYMENT.md](DEPLOYMENT.md) for what remains.

---

## 1. What exists right now

```
cadence/                   Django project package
├── settings.py             env-driven config, production hardening gated on DEBUG=0
├── celery.py                Celery app, wired to Django settings
└── urls.py                  admin, auth, and the three apps' urls.py included

projects/                  Who is working, on what, and who can do what
├── models.py                Project, Member
├── permissions.py            can_view/can_edit/can_manage — role checks
├── views_base.py              ProjectPermissionMixin — every view inherits this
├── views.py / urls.py         Screen: project list (the landing page)
├── management/commands/       seed_demo — the whole demo, built by hand and verified
└── admin.py

tasks/                     What needs doing, and the dependency graph
├── models.py                Task, TaskDependency
├── services.py               would_create_cycle() — the DFS cycle detector
├── views.py / urls.py         Screens 1-3: board, task detail, add-dependency (HTMX)
└── admin.py

sprints/                   Planning windows, capacity, burndown
├── models.py                Sprint (+ thin start()/add_task() wrappers), SprintCommitment,
│                             Capacity, TimeOff, WorkLog
├── services.py               capacity_for(), start_sprint(), scope_creep_tasks(),
│                             write_daily_worklogs(), velocity(), and friends
├── views.py / urls.py         Screens 4-5: capacity, sprint detail + burndown
├── tasks.py                   Celery task: write_daily_worklogs_for_active_sprints
├── management/commands/       write_worklogs — run the nightly job by hand
└── admin.py

templates/                 Django templates + Tailwind (CDN) + HTMX (CDN)
├── base.html                 nav, messages, htmx/tailwind script tags
├── registration/login.html
├── projects/, tasks/, sprints/  one template per screen, one HTMX partial
                                 (tasks/_dependencies.html) swapped in place

tests/
├── factories.py             factory_boy factories for every model
├── test_smoke.py             1 test — the app boots and a Task can be made
├── test_dependency_graph.py  17 tests — cycle detection (TEST_PLAN.md §1)
├── test_blocking.py          7 tests — derived is_blocked (TEST_PLAN.md §2)
├── test_capacity.py          15 tests — capacity arithmetic, time off, allocation, frozen snapshot (TEST_PLAN.md §3)
├── test_sprints.py           13 tests — start_sprint atomicity, scope creep, burndown, velocity (TEST_PLAN.md §4)
├── test_permissions.py       9 tests — role checks, HTTP 404-not-403, URLconf mixin walk (TEST_PLAN.md §5)
└── test_queries.py           3 tests — board/capacity run in constant queries (TEST_PLAN.md §6)

.github/workflows/ci.yml    ruff + pytest against real postgres/redis, on push and PR
docker-compose.yml          postgres, redis, web, worker, beat — 5 services
Dockerfile                  python:3.12-slim, requirements-dev installed
```

**65 tests, all green.** `docker compose up` brings up all five services;
`migrate` runs clean; `seed_demo` builds the full demo project; the admin
lists all nine models across the three apps and is reachable only by the
manager login.

---

## 2. The order things were built in, and why

### Step 1 — Foundation, the boring-but-necessary part

Before any business logic, the project needed to actually run. That meant,
in order:

1. **`.gitignore`** first, so nothing generated (caches, `.env`, `db.sqlite3`)
   could accidentally get committed later.
2. **`requirements.txt` / `requirements-dev.txt`** split — runtime deps vs.
   test tooling (pytest, factory_boy, freezegun, ruff) — so a production
   image doesn't have to carry test dependencies later, without having to
   rework the list now.
3. **Dockerfile + docker-compose.yml** — `web`, `postgres`, `redis`,
   `worker`, `beat` as five separate services, matching
   [SETUP.md](SETUP.md)'s port layout (`8005`, `5437`) offset from other
   projects on the same machine.
4. **`django-admin startproject`**, committed raw first, *then* rewritten —
   so the diff between "what django-admin generates" and "what this project
   actually needs" is visible in git history instead of buried in one commit.

**The settings rewrite** is the one worth reading directly
([cadence/settings.py](../cadence/settings.py)): `SECRET_KEY` has no
`default=` in its `config()` call, so a missing one fails at startup instead
of running insecurely — this was a deliberate line from
[SETUP.md](SETUP.md), not an accident. `DATABASE_URL` is parsed by hand with
`urllib.parse` rather than pulling in `dj-database-url` for one call site.

### Step 2 — Models, first as one app, then split into three

The nine models from [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) §1 were first
written into a single `core` app (commits `924851a` through `f27e6cc`), to
get the schema and constraints right without also juggling app boundaries.
Once the schema was correct and migrating cleanly, the project was
**restructured into `projects` / `tasks` / `sprints`** (commit `e31f55f`
onward) — one app per domain, each with its own `models.py`, `admin.py`,
and (for `tasks`) `services.py`.

Why split at all, for nine models: a single `core` app is fine at this size,
but it doesn't demonstrate how the project would be organized if it grew —
and the split costs almost nothing here, since Django's migration framework
resolves the one circular reference (`tasks.Task.sprint` needs
`sprints.Sprint`; `sprints.SprintCommitment` and `sprints.WorkLog` need
`tasks.Task`) automatically by splitting `sprints`'s initial migration in
two (`0001_initial.py` creates the models, `0002_initial.py` adds the FKs
into `tasks`, applied after `tasks.0001_initial`). The FK across the
circular edge is declared as a string (`"sprints.Sprint"`,
`"tasks.Task"`) rather than an import, which is what makes the split
possible without a shared "base" app.

**Business logic lives in `services.py`, not in the model.** The cycle
detector (`would_create_cycle`) is a plain function in
[tasks/services.py](../tasks/services.py) that takes two `Task` instances
and returns either `None` or the cycle path. `TaskDependency.clean()` is
three lines that call it. This split exists so the algorithm can be reasoned
about (and tested, in principle) independently of the ORM model that happens
to use it — and so the model file stays a readable list of fields rather
than growing a graph algorithm inside it. As more phases land (capacity,
sprint start), the same pattern applies: `sprints/services.py` will hold
`capacity_for()` and the sprint-start transaction, not the `Sprint` model
itself.

Each model group landed as its own commit — `Project`+`Member`, then
`Sprint`+`Task`, then `TaskDependency` (with the cycle logic), then the
remaining four sprint-adjacent models — so that a broken migration or a
wrong constraint would show up against a small diff, not a 150-line one.

### Step 3 — The cycle detector, and proving it with tests before trusting it

[TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) §2 specifies the algorithm: walk
forward from `depends_on`, and if the walk reaches `task`, the new edge
would close a loop. The implementation
([tasks/services.py](../tasks/services.py)) is an iterative DFS (no
recursion limit risk on a long chain) that tracks the path taken so far, so
a rejected edge can report the *actual* cycle — `CAD-3 -> CAD-7 -> CAD-3` —
rather than just "no."

**`seen` is the one line that makes a diamond legal.** `A->B`, `A->C`,
`B->D`, `C->D` reaches `D` twice during the walk from `A`; without
tracking visited nodes, the second arrival looks like a revisit and a naive
implementation calls it a cycle. This is called out directly in the code
comment, in the spec, and in the test suite, because it's the mistake this
whole design exists to avoid — see `test_diamond_is_allowed` in
[tests/test_dependency_graph.py](../tests/test_dependency_graph.py).

The test file has three layers, deliberately in this order of importance:

1. **Cases that must be rejected** — direct cycle, 3-node, 5-node, self-
   dependency (enforced at the DB level via a `CHECK` constraint, not just
   in Python), a 20-node chain closing at the far end.
2. **Cases that must be *allowed*** — the diamond, fan-in, fan-out, two
   independent chains in one project, a 50-node linear chain, a
   two-level-deep diamond. **These tests matter more than the rejections**:
   a detector that rejects every single edge would pass every test in
   group 1 and fail every test in group 2, and only group 2 catches that.
3. **The invariant test** — 200 random edge attempts against a 30-node
   graph, checked afterwards by a *second, independently written* DFS
   (`graph_contains_cycle` inside the test file, not importing
   `would_create_cycle`) to confirm no cycle survived. Seeded
   (`random.seed(1234)`) so a failure is reproducible.

Enforcement is also tested at more than one entry point:
`test_cycle_is_rejected_in_the_admin` calls `full_clean()` the way
`ModelAdmin` does; `test_cycle_is_rejected_via_the_form` builds a real
`ModelForm` and checks `form.is_valid()`. Both matter because the rule
lives in `TaskDependency.clean()` — one place — precisely so it can't be
bypassed by adding a new entry point later (a view, an API endpoint) that
forgets to re-check it.

One test from [TEST_PLAN.md](TEST_PLAN.md) §2 was **deliberately skipped**:
`test_a_blocked_task_cannot_be_moved_to_in_progress`. It requires a state-
transition guard that doesn't exist yet — that's new behaviour, not
something Phase 2 ("models + one test file, no views") covers, so it's
left for whichever phase adds transition enforcement, with a note in the
commit message rather than silently dropped.

### Step 4 — Derived status, proved by *absence* of a write

`Task.is_blocked` ([tasks/models.py](../tasks/models.py)) is a property, not
a column: `self.dependencies.exclude(depends_on__state=Task.State.DONE).exists()`.
Nothing sets it, nothing signals on it. The test that matters most here is
`test_completing_the_last_dependency_unblocks_with_no_write` — it completes
task A, re-fetches task B from the database, and asserts `B.is_blocked` is
now `False` while confirming `B`'s own row (`created_at`) was never touched.
The property just computes a different answer on the next read, which is
the entire point of deriving it instead of storing it — see
[TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) §3 for the "why not store it"
reasoning in full.

### Step 5 — Capacity arithmetic, same services.py pattern as tasks

[sprints/services.py](../sprints/services.py) holds three functions:
`capacity_for(member, sprint)`, `allocated_hours_for(member, sprint)`, and
`is_over_allocated(member, sprint)`. None of them touch the database beyond
reading — nothing here is stored yet, because storing capacity only makes
sense as a snapshot taken at sprint start (Phase 4), and there's no
`Sprint.start()` yet to take it.

The one part of the formula worth reading closely is
`timeoff_hours_for()`: it doesn't just count the days in a `TimeOff` range,
it clips that range to the sprint window first (`max(starts)`/`min(ends)`)
and then counts only weekdays inside the clipped range. That clip is what
makes `test_timeoff_partially_overlapping_the_sprint_reduces_only_the_overlap`
pass — leave that starts before the sprint and ends inside it should only
cost the days actually inside the sprint. The weekday-only counting is what
makes `test_weekend_inside_a_leave_range_does_not_reduce_capacity` pass — a
Saturday inside someone's leave was never sprint capacity to begin with.

`is_over_allocated` returns a plain boolean, and nothing in the codebase
stops a task from being assigned once it's `True` — per
[TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) §4, over-allocation is meant to warn,
never block, and there's no save-time check anywhere that would prevent it.

`test_capacity_is_frozen_at_sprint_start` — the one test from
[TEST_PLAN.md](TEST_PLAN.md) §3 that needed `Sprint.start()` to exist — was
added once Step 6 below landed, closing out §3 entirely.

### Step 6 — Sprint lifecycle: start, scope creep, burndown, velocity

Four things landed together here, all in
[sprints/services.py](../sprints/services.py), because they build on each
other in the order [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) §5 describes them:

**`start_sprint()`** is the one place in the codebase using
`@transaction.atomic` so far. It writes a `SprintCommitment` row (copying
the current estimate) for every task in the sprint, computes and stores a
`Capacity` row for every project member via the `capacity_for()` from Step
5, then stamps `started_at` — all three, or none of them, which is what
`test_starting_a_sprint_is_atomic` forces by tripping the unique constraint
on `SprintCommitment` partway through and asserting the sprint never
flipped to `active`. Calling `start()` on anything but a `planned` sprint
raises `SprintAlreadyStartedError` rather than silently re-snapshotting —
re-running it would let a live sprint's capacity quietly drift from what
was actually committed to.

**Scope creep has no field.** `scope_creep_tasks()` is one line —
`sprint.tasks.exclude(commitments__sprint=sprint)` — tasks in the sprint
with no matching commitment row. `add_task_to_sprint()` deliberately does
*not* create a commitment; the row's absence is the entire signal. This
mirrors how `Task.is_blocked` was derived in Step 4 rather than stored, and
`test_scope_creep_is_the_absence_of_a_commitment_row` asserts directly that
no such flag exists anywhere on `Task` or `SprintCommitment`.

**`committed_hours()` and `added_hours()` are two separate sums**, not one
number with a footnote — committed reads `estimate_hours_at_start` off the
frozen `SprintCommitment` rows, added reads the *current* `estimate_hours`
off whatever `scope_creep_tasks()` returns (those were never frozen, so
there's nothing to re-read from). Keeping them separate all the way down is
what let `test_burndown_separates_committed_from_added` assert the two
numbers don't silently merge.

**`write_daily_worklogs()`** snapshots `remaining_hours` (= current
estimate, or zero if unestimated) into one `WorkLog` row per unfinished
task, keyed on `(task, date)` via `update_or_create` so re-running it for
the same day is harmless. It's wired to actually run nightly in
[sprints/tasks.py](../sprints/tasks.py) (a `@shared_task` iterating every
active sprint) via `CELERY_BEAT_SCHEDULE` in
[cadence/settings.py](../cadence/settings.py) — `django_celery_beat` is
installed but not used as the scheduler backend here, since a static
crontab is simpler for the one recurring job this project has. The
`write_worklogs` management command
([sprints/management/commands/write_worklogs.py](../sprints/management/commands/write_worklogs.py))
calls the same task by hand, exactly as [SETUP.md](SETUP.md) describes.

**`velocity()`** averages `committed_hours()` — never `added_hours()` —
across the most recently completed sprints, and returns `None` until at
least three exist. `test_velocity_uses_committed_hours_only` adds 99 hours
of scope creep to three completed sprints specifically to prove it gets
ignored; a fast-looking chaotic sprint should never inflate the next
sprint's plan.

### Step 7 — Permissions, the five screens, and the N+1 bugs they surfaced

**Permissions first, because every view depends on it.**
[projects/permissions.py](../projects/permissions.py) is three one-line
functions (`can_view`/`can_edit`/`can_manage`) checking a `Member.role`.
[projects/views_base.py](../projects/views_base.py)'s `ProjectPermissionMixin`
resolves the project from the URL and 404s — never 403s — a non-member,
because a 403 would itself leak that the project exists to someone who
shouldn't know that. Every project-scoped view inherits it, and
`tests/test_permissions.py::test_every_project_scoped_view_uses_the_permission_mixin`
walks the actual URLconf and fails the suite if a new view forgets to.

**The five screens** (docs/UI_FLOW.md) went in as: board and task detail
(read-only), add-dependency (the HTMX interaction, wired straight to the
same `TaskDependency.clean()` from Step 3 — the exact same
`ValidationError` renders as the on-page cycle box, no separate error
handling path to keep in sync), state-change (server-enforced independent
of the disabled `<select>`), capacity, and sprint detail with the burndown
drawn as CSS bars (no charting library — one `<div>` per day, height set by
`{% widthratio %}`).

**Two N+1 bugs surfaced immediately** once real query counts were measured
— logged in full in DECISIONS.md, summarized here: `Task.is_blocked`'s
`.exclude().exists()` ignored `prefetch_related` entirely and queried once
per task regardless, and the board's `select_related` was missing
`project`, so `task.key` lazy-loaded it once per task too. Both fixed
(`is_blocked` now checks `_prefetched_objects_cache` before falling back to
a live query), both pinned at a constant query count in
[tests/test_queries.py](../tests/test_queries.py) — verified by hand at
both 45 and 90 tasks that the count didn't move. The capacity view got the
same treatment preemptively: it batches `Capacity`/`TimeOff`/assigned-task
lookups into three queries total rather than looping per member, which
`test_capacity_view_does_not_scale_queries_with_members` confirms at 1
member and at 11.

**`seed_demo`** is the last piece, and per docs/UI_FLOW.md it's treated as
the demo, not a fixture. Every line in that doc's requirements table is
built and was verified by hand, not assumed: the cycle pair is fixed at
CAD-3/CAD-7 to match docs/DEMO_SCRIPT.md exactly (an `assert` in the
seeder itself catches if a future edit makes the numbering drift), the
4+-deep chain and the diamond both exist in the actual seeded graph (walked
by hand to confirm depth 6, not estimated), two members
(Priya, Vikram) are genuinely over capacity per `is_over_allocated()`, and
186 `WorkLog` rows exist across the sprint rather than two endpoints. The
manager login was also given `is_staff=True` — easy to miss, since nothing
about "the demo has three role logins" implies one of them needs a
Django-specific flag to reach `/admin/` at all.

---

## 3. How to see it work right now

```bash
cp .env.example .env
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
docker compose exec web pytest -v
```

Then open `http://localhost:8005/` and log in as `manager@cadence.demo` /
`password` (see [SETUP.md](SETUP.md) for the other two logins). From the
board: click into **CAD-3** (API keys), add a dependency on **CAD-7**
(Payment gateway) — it rejects with the exact cycle path, live, no shell
required. That is the whole [DEMO_SCRIPT.md](DEMO_SCRIPT.md) walkthrough,
now actually clickable rather than something to imagine from the docs.

---

## 4. What's next

Only one phase is left, per [BUILD_PLAN.md](BUILD_PLAN.md):

- **Phase 1-5 are done.** Foundation, the dependency graph, capacity,
  sprint lifecycle, and the UI — permissions, all five screens, and
  `seed_demo` — are all built and tested (65 tests). The nightly `WorkLog`
  Celery task was verified end to end through the real broker (dispatched
  with `.delay()`, confirmed received and succeeded in the worker log —
  see DECISIONS.md for the stale-worker-registry bug that surfaced while
  checking this). The one intentionally-skipped test from Phase 2
  (a state-transition guard on blocked tasks beyond what
  `TaskStateChangeView` already enforces server-side) remains open — it
  was never blocking, just deferred.
- **Phase 6 — Deploy** — Railway + Neon, per
  [DEPLOYMENT.md](DEPLOYMENT.md). This is the one phase left, and it is
  being done by hand rather than by this assistant — see that doc's
  checklist for the exact steps.
