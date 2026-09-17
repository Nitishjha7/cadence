# Decisions

A running log of every non-obvious decision, **written at the time it is made**.

## Why this file exists

An interviewer will not read the code. They will point at something and ask "why
is it like that?". This file is where that answer lives while it is still fresh.

Written as you go, it is an honest record of the reasoning. Written afterwards
from memory, it is a reconstruction — and it reads like one.

## How to write an entry

Three to six lines. Date, what was chosen, what was rejected, and **why**.

The "what was rejected" line matters most. A decision with no alternative
considered is not a decision, it is a default.

```markdown
## YYYY-MM-DD — Short title

What was chosen. What the alternative was. Why the alternative loses. What it
costs (every decision costs something).
```

Also log **bugs that surprised you**. Those are the strongest interview material
available, and they are forgotten within a week if not written down.

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

## Entries from here are written as the code is built

Things that will need an entry:

- Whether `seen` handling in the DFS needed adjusting once real graphs appeared
- What the first genuinely surprising graph bug turns out to be (there will be one)
- Whether capacity needed a holiday calendar sooner than expected
- How concurrent dependency writes are handled, if at all
- Any bug that took more than an hour — especially the ones that were not the
  obvious cause
