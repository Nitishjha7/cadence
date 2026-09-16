# Build Plan

Six phases, in order. Roughly ten working days.

The rule throughout: **the core is built before anything that displays it.** A
cycle detector with no screen is still a working cycle detector; a board with no
graph logic is a mockup.

---

## Phase 1 — Foundation (1 day)

**Goal:** `python manage.py migrate` runs clean and the container comes up.

- Django 5, Python 3.12, PostgreSQL 16, Redis — Docker Compose
- All nine models ([TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) §1)
- The `UNIQUE (task, depends_on)` and self-dependency `CHECK` constraints go in
  **now**, with the first migration — they are the design, not a later hardening
  step
- `Task.STATE_CHOICES` has exactly three values and **`blocked` is not one of
  them**, from the first migration. Adding it later is the mistake this design
  exists to avoid.
- Django admin registered for every model
- factory_boy factories
- pytest + pytest-django, one smoke test green

**Done when:** `docker compose up`, `migrate`, and `pytest` all pass, and the admin
lists every model.

---

## Phase 2 — Dependency graph (2–3 days) — the core

**Goal:** cycle detection is complete and pinned by ~25 tests.

**No views. No templates.** Models, one function, one test file.

- `would_create_cycle(task, depends_on)` — iterative DFS
- Wired into `TaskDependency.clean()` so it applies to admin, forms and API alike
- The error message names the **actual path**
- `Task.is_blocked` as a derived property
- Every test in [TEST_PLAN.md](TEST_PLAN.md) §1 and §2

**The tests that matter most are the ones that must pass, not the ones that must
fail.** A detector that rejects everything passes every cycle test. Write
`test_diamond_is_allowed` early.

**Spend the extra day here if it needs one.** This phase is the project.

**Done when:** ~37 tests green, including the random-graph invariant test with an
independent checker.

---

## Phase 3 — Capacity (2 days)

**Goal:** capacity and allocation are correct, including leave.

- `capacity_for(member, sprint)` — weekly hours scaled to sprint length
- Time-off subtraction counting **working days only**
- Allocation summing assigned unfinished estimates
- Unestimated tasks counted as zero and reported separately
- Over-allocation flagged, never blocked
- All of [TEST_PLAN.md](TEST_PLAN.md) §3

**Done when:** a member on three days leave in a two-week sprint reports 16 hours,
not 40, and assigning them more work still succeeds with a warning.

---

## Phase 4 — Sprints, snapshot and burndown (2 days)

**Goal:** starting a sprint freezes scope, and the burndown can tell the truth.

- `Sprint.start()` — commitments + capacity + timestamp, in one transaction
- Scope creep as **the absence of a commitment row** (no new flag)
- Nightly Celery task writing `WorkLog` rows
- Burndown series — committed and added kept separate
- Velocity from the last three completed sprints, committed hours only
- All of [TEST_PLAN.md](TEST_PLAN.md) §4

**Done when:** a task added on day 8 of an active sprint appears as added scope and
produces a visible step in the burndown series.

---

## Phase 5 — UI, permissions and seeder (2 days)

**Goal:** the demo in [DEMO_SCRIPT.md](DEMO_SCRIPT.md) can be performed end to end.

- The five screens in [UI_FLOW.md](UI_FLOW.md) — Django templates + Tailwind
  defaults, HTMX for the inline dependency form
- **The cycle rejection box** — the single most important interaction
- Permission mixin on every view, plus the URLconf-walking test
  ([TEST_PLAN.md](TEST_PLAN.md) §5)
- Query-count tests ([TEST_PLAN.md](TEST_PLAN.md) §6) — `is_blocked` makes N+1 the
  natural failure mode
- **`seed_demo`** — the full specification at the end of [UI_FLOW.md](UI_FLOW.md)

The seeder is not a chore at the end. It decides whether the demo reads as real.
Budget for it properly, and **verify the cycle demo reproduces** after it runs.

**Done when:** the four-minute demo runs without touching the database by hand.

---

## Phase 6 — Deploy and document (1 day)

**Goal:** a live URL in the README.

- Railway or Render, with a managed Postgres
- Demo logins for all three roles — the permission model is worth showing
- **Real screenshots** replacing the ASCII sketches in [UI_FLOW.md](UI_FLOW.md)
- README rewritten to describe what exists, "not built yet" banner removed
- README numbers taken from the actual test run, not estimated
- CI — lint and tests on push

**Done when:** someone can click a link, log in as a manager, and see the board.

---

## What is not in any phase

Deliberately, and each for a reason given in the README:

- Drag-and-drop board
- Real-time collaborative updates
- Comments, attachments, custom fields
- Time tracking (actuals)
- Multiple projects per sprint

---

## The habit that matters more than the phases

**Write `DECISIONS.md` as you go, not afterwards.**

Every time a choice is made that could have gone another way, three lines:

```markdown
## 2026-09-25 — Blocked is derived, not stored

Computed from dependencies rather than a stored field. Stored would need
updating on every dependency state change, and the first missed update gives a
tool that says "ready" about something that is not. Costs an N+1 on the board,
handled with prefetch and pinned by a query-count test.
```

Written at the time, this is an honest record of the reasoning. Written afterwards
from memory, it is a reconstruction — and it reads like one.

It is also the file that makes "why did you do it that way?" a comfortable
question rather than a threatening one.
