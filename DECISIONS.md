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

## Entries from here are written as the code is built

Things that will need an entry:

- Whether `seen` handling in the DFS needed adjusting once real graphs appeared
- What the first genuinely surprising graph bug turns out to be (there will be one)
- Whether capacity needed a holiday calendar sooner than expected
- How concurrent dependency writes are handled, if at all
- Any bug that took more than an hour — especially the ones that were not the
  obvious cause
