# Decisions

A running log of every non-obvious decision, **written at the time it is made**.

## Why this file exists

Code doesn't say why it's like that. This is where that reasoning lives
while it's still fresh — written at the time, not reconstructed later from
memory, which tends to smooth over the actual trade-offs that were made.

## How I write an entry

Date, what I chose, what I rejected, and why. The "what was rejected" line
matters most — a decision with no alternative considered isn't really a
decision, it's just a default.

```markdown
## YYYY-MM-DD — Short title

What was chosen. What the alternative was. Why the alternative loses. What it
costs (every decision costs something).
```

Bugs that surprised me go here too, since they're forgotten within a week
otherwise.

---

## 2026-09-16 — Why this project at all

Portfolio was entirely Python web APIs and agentic work, with no Django project.
Applying for Django roles with no Django project is a screening problem before it
is anything else.

Chose a planning tool over a CRUD app because the two questions at its centre —
can a task start, and does anyone have room — are a graph problem and an
arithmetic problem. Server-rendered pages, auth and roles, and admin as a
back-office console are what Django is actually for.

Rejected: a helpdesk/ticketing system, because "ticket" collides with an unrelated
project in the portfolio and invites the wrong comparison. Also rejected framing
this as a "Jira clone" — a board with drag-and-drop is CRUD with a nice front end.

---

## 2026-09-16 — Not building drag-and-drop

The most visually impressive part of a tool like this teaches nothing and costs
days of front-end work. Those days go into the dependency graph instead.

Cost: the demo looks plainer than a board product. Accepted, because the demo is
about the cycle rejection and the capacity arithmetic, not the cards.

---

## 2026-09-17 — One `core` app first, then split into `projects` / `tasks` / `sprints`

All nine models were built inside a single `core` app first, to get the
schema and constraints right without also juggling app boundaries. Once
migrations were clean and the first tests passed, the project was
restructured into three domain apps — `projects`, `tasks`, `sprints` — each
with its own `models.py`, `admin.py`, and (for `tasks`) `services.py` for
business logic that isn't just fields.

Rejected: keeping `core` as-is. Nine models is genuinely small enough that
one app would work, but it doesn't demonstrate how this project would be
organized if it grew, and the split is nearly free — Django's migrations
handle the one circular FK (`tasks.Task.sprint` needs `sprints.Sprint`;
`sprints.SprintCommitment`/`WorkLog` need `tasks.Task`) automatically by
splitting `sprints`'s initial migration into two files, applied around
`tasks.0001_initial`.

Cost: string-based FK references (`"sprints.Sprint"`, `"tasks.Task"`)
instead of direct imports across the two apps, and slightly more
boilerplate (three `admin.py`/`apps.py` pairs instead of one). Also moved
`would_create_cycle` out of the model file into `tasks/services.py` at the
same time — same algorithm, no behaviour change, just kept the model file
from growing a graph algorithm inside it.

---

## 2026-09-26 — Static `CELERY_BEAT_SCHEDULE`, not `django_celery_beat` as the scheduler

`django_celery_beat` is installed (it was in the original requirements list
for its database-backed periodic task model, useful if schedules ever
needed to be editable per-project from the admin). For the one recurring
job this project actually has — the nightly worklog snapshot — a static
entry in `CELERY_BEAT_SCHEDULE` is simpler: one dict in settings.py, no
extra migration, no admin UI to maintain for a schedule that never changes.

Rejected: registering the job as a `PeriodicTask` row via
`django_celery_beat`, which is the "more Django admin, less code" option.
Not worth it for a single job with a schedule that isn't meant to be
edited by a non-technical user. The app stays installed since the model is
harmless to have around and documents the option for later.

Cost: if a second recurring job ever needs a schedule editable at runtime,
this decision gets revisited — but that's a real trade to make then, not a
guess to make now.

---

## 2026-09-26 — `start_sprint()` forbids re-starting instead of being idempotent

Calling `.start()` on anything but a `planned` sprint raises
`SprintAlreadyStartedError` rather than silently no-op'ing or
re-snapshotting. The alternative — making it idempotent, so calling it
twice is harmless — sounds safer but isn't: re-running it would recompute
`Capacity` and re-copy `estimate_hours_at_start` against whatever the
member's leave and task estimates happen to be *right now*, which is
exactly the kind of drift the snapshot exists to prevent
([TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) §5). A loud, specific
exception is cheaper to debug than a sprint whose committed numbers
quietly moved between two page loads.

Cost: any caller (a future view, an API) has to catch this exception and
turn it into a normal "already started" message instead of relying on the
function being safe to call blindly.

---

## 2026-09-26 — Board's is_blocked N+1 survived prefetch_related

`assertNumQueries` caught two bugs prefetch_related was supposed to
prevent: `Task.is_blocked` called `.exclude().exists()` directly, which
issues a fresh query regardless of any prefetch cache, and the board's
`select_related` was missing `project`, so `task.key` (used in both the
board and the dependency list) lazy-loaded it once per task.

Fixed both: `is_blocked` now reuses the prefetch cache when present
(`_prefetched_objects_cache`) instead of falling back to a live query, and
`select_related` picked up `project`. Query-count tests now pin both views
at a constant count.

Rejected: leaving `is_blocked` as a plain query and just prefetching harder.
There's no `prefetch_related` incantation that stops a property from
issuing its own query when called — the property itself has to be taught
to look for cached data first.

Cost: `is_blocked` now has two code paths (prefetched vs. not), which is one
more thing to keep in sync if the prefetch shape ever changes — the docstring
points at tests/test_queries.py specifically so a future change gets caught.

---

## 2026-09-26 — Single settings.py with DEBUG-gated blocks, not a settings/ package

docs/DEPLOYMENT.md originally sketched `DJANGO_SETTINGS_MODULE=cadence.settings.production`
as a separate module. Built it instead as one `cadence/settings.py` with a
`if not DEBUG:` block at the end adding SSL redirect, secure cookies, and
HSTS. There is exactly one deploy target for this project (Railway) and no
staging/prod split — a `settings/base.py` + `settings/production.py` split
earns its complexity on a project with multiple environments to diverge
between, and this isn't one.

Rejected: the settings-package split from the original deployment sketch.
Cost: if a real staging environment is ever added, this gets revisited —
env-var-gated blocks in one file stop being clearly better once there are
three or four environments instead of two.

---

## 2026-09-26 — Bug that surprised me: worker container didn't see the new Celery task after adding it

Added `sprints/tasks.py` (the nightly worklog task) while `worker`/`beat`
containers from an earlier `docker compose up` were still running. Manually
dispatching the task with `.delay()` hit `KeyError: 'sprints.tasks.write_daily_worklogs_for_active_sprints'`
in the worker log — the task wasn't in its registry at all, despite the
file being on disk (bind-mounted, so the container could see it).

Cause: `celery -A cadence worker` builds its task registry once, at process
start, via `app.autodiscover_tasks()`. A bind mount syncs the *file*, but
not the *running Python process's* imports — the worker had no reason to
re-import `sprints.tasks` just because a new file appeared next to the ones
it already loaded. `docker compose restart worker beat` fixed it
immediately: same image, same volume, fresh process, task registered.

Worth remembering for Railway too: each of the three services
(web/worker/beat) is a separate long-running process from the same image,
and none of them auto-reloads on a new deploy — a deploy has to actually
restart the worker/beat processes, not just push new code and assume
they'll notice.

---

More entries get added here as the project keeps changing.
