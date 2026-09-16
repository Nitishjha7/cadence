# UI Flow

The five screens, what each one shows, and the seed data that makes them look
real. The timed walkthrough is in [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

Django templates + HTMX, server-rendered. No SPA — the point is that this is a
classic server-rendered application, which is what Django is for. HTMX handles the
few places that need a partial update (inline dependency add, state change).

---

## Design rule: do not spend time on beauty

Tailwind defaults. Tables, badges, cards. No drag-and-drop, no animation.

An interviewer is not judging the CSS. They are looking at **what is behind the
screen**. The cycle-rejection box can look plain — the fact that it names the
actual path is the thing being demonstrated.

Time saved on visual polish goes into the seed data, which is what decides whether
the demo reads as real.

---

## The five screens

| # | Route | Screen | The thing it exists to show |
|---|---|---|---|
| 1 | `/projects/{id}/board/` | Board | Blocked tasks, derived not set |
| 2 | `/tasks/{id}/` | Task detail | Dependencies in both directions |
| 3 | (inline on task detail) | Add dependency | **Cycle rejection — the core** |
| 4 | `/sprints/{id}/capacity/` | Capacity | Load bars, leave, over-allocation |
| 5 | `/sprints/{id}/` | Sprint + burndown | Scope creep, visibly |

That is the whole application.

---

## 1. Board

```
+--------------------------------------------------------------------+
|  Cadence / Payments Revamp                      Sprint 12 (active) |
+--------------------------------------------------------------------+
|                                                                    |
|  TO DO                    IN PROGRESS            DONE              |
|  ---------------------    -------------------    ----------------  |
|  CAD-14 Webhook retry     CAD-9  Card form       CAD-3  API keys   |
|  Rahul - 8h               Priya - 5h             Rahul - 3h        |
|                                                                    |
|  [L] CAD-7 Payment gw     CAD-12 Refund flow     CAD-5  DB schema  |
|  blocked by CAD-14        Amit - 8h              Sneha - 5h        |
|  Amit - 13h                                                        |
|                                                                    |
|  [L] CAD-18 Settlement                                             |
|  blocked by CAD-7, CAD-12                                          |
|  unassigned - no estimate                                          |
|                                                                    |
+--------------------------------------------------------------------+
```

`[L]` is a lock icon. Blocked tasks are greyed and name what blocks them.

**What this screen has to communicate without being told:** the lock is not a
status someone chose. It is a consequence.

**Seed requirements:**

- 45ish tasks so the columns are full
- Several blocked, at least one blocked by **two** dependencies
- At least one task with no estimate — capacity has to handle it and the UI has to
  show it
- A mix of assignees, and some unassigned

---

## 2. Task detail

```
+----------------------------------------------------------+
|  CAD-7  Payment gateway integration                      |
|  In sprint 12 - Amit Kumar - 13h estimate                |
|  State: To do          [L] Blocked                       |
+----------------------------------------------------------+
|                                                          |
|  Blocked by                                              |
|    CAD-14  Webhook retry logic        To do      [x]     |
|                                                          |
|  Blocks                                                  |
|    CAD-18  Settlement reconciliation  To do              |
|                                                          |
|  [ + Add dependency ]                                    |
|                                                          |
+----------------------------------------------------------+
```

Both directions are shown. "Blocks" is the reverse relation and is what makes the
graph feel like a graph rather than a list of prerequisites.

The state selector is **disabled while blocked**, with a tooltip: *"CAD-14 must be
done first."*

---

## 3. Add dependency — the cycle rejection

**This is the most important interaction in the application.**

Clicking `+ Add dependency` opens an inline HTMX form with a task picker. On
submit, the server validates before saving.

**Success** — the row appears in the list, no page reload.

**Rejection** — the form is replaced with the error:

```
+-----------------------------------------------------------+
|  !  Circular dependency                                   |
|                                                           |
|     This would create a cycle:                            |
|                                                           |
|       CAD-3 (API keys)                                    |
|         -> CAD-7 (Payment gateway)                        |
|         -> CAD-3 (API keys)                               |
|                                                           |
|     Neither task could ever start.                        |
|                                                           |
|                                    [ Try another task ]   |
+-----------------------------------------------------------+
```

**Why the path matters.** "Invalid dependency" tells the user they are wrong.
Naming the loop tells them *what* is wrong, and it is the visible output of the
DFS — the error is the algorithm showing its work.

For the demo, the seed data must contain a pair of tasks where this can be
triggered in two clicks. It is worth checking after every seeder change that the
cycle demo still reproduces.

---

## 4. Capacity

```
+--------------------------------------------------------------------+
|  Sprint 12 capacity            01 Sep - 14 Sep 2026               |
|                                                                    |
|  Team:  187h allocated / 152h available      ! over capacity      |
+--------------------------------------------------------------------+
|                                                                    |
|  Rahul Sharma    ####################====  52 / 40h   ! over      |
|                                                                    |
|  Priya Mehta     ######                    16 / 16h               |
|                  on leave 08-10 Sep (3 days)                      |
|                                                                    |
|  Amit Kumar      ############              31 / 40h               |
|                  2 tasks unestimated                              |
|                                                                    |
|  Sneha Patel     ##################==      45 / 40h   ! over      |
|                                                                    |
|  Vikram Singh    ##########                24 / 40h               |
|                                                                    |
+--------------------------------------------------------------------+
```

Three things this screen has to make obvious:

- **Priya's capacity is 16, not 40** — leave reduced it, and the screen says why
- **Amit has unestimated work** — counted as zero, flagged, not hidden
- **Over-allocation is a warning** — amber, not a blocked action

The bar overflows past the limit rather than capping at 100%. A capped bar hides
how bad the overload is.

---

## 5. Sprint and burndown

```
+--------------------------------------------------------------------+
|  Sprint 12                     01 Sep - 14 Sep    * Active        |
|                                                                    |
|  Committed  152h        Added  16h        Completed  94h          |
+--------------------------------------------------------------------+
|                                                                    |
|  160 |***                                                          |
|      |   ***                                                       |
|  120 |      ****                                                   |
|      |          **___                                              |
|   80 |              |  \____                                       |
|      |              |       \___                                   |
|   40 |              |           \____                              |
|      |              |                \___                          |
|    0 +--------------|---------------------------                   |
|      1   3   5   7  |  9   11  13                                  |
|                     |                                              |
|                     +-- 08 Sep: 2 tasks added (+16h)              |
|                                                                    |
|      *** ideal      --- actual                                     |
+--------------------------------------------------------------------+
|                                                                    |
|  Scope added after start                                           |
|    CAD-31  Fraud check hook        8h    added 08 Sep             |
|    CAD-32  Retry backoff tuning    8h    added 08 Sep             |
|                                                                    |
|  Velocity (last 3 sprints): 138h avg committed-completed          |
+--------------------------------------------------------------------+
```

**The step up on 08 Sep is the whole point of this screen.** Without the sprint
snapshot the line would simply have flattened, and a sprint that took on 16 extra
hours would look identical to one that planned correctly.

The added tasks are listed underneath by name, so the step is explained rather
than just visible.

---

## Empty states

- Project with no tasks — *"No tasks yet."* plus a create button
- Sprint not started — *"This sprint has not started. Capacity and burndown appear
  once it does."*, which also teaches the snapshot behaviour
- Member with nothing assigned — a zero bar, not a missing row

---

## Seed data specification

`python manage.py seed_demo`

The seeder is the most important piece of demo infrastructure in the project.

| Requirement | Why |
|---|---|
| **1 project, ~45 tasks** | Enough that the board looks worked-in |
| **3 sprints — 2 completed, 1 active** | Velocity needs history; the active one is the demo |
| **6 members, mixed roles** | Permissions have something to enforce |
| **A dependency chain 4+ deep** | So "blocked by" is not all one level |
| **A diamond in the graph** | Proves the legal case exists in real data |
| **A pair that triggers a cycle** | The demo needs it reproducible in two clicks |
| **One member on leave mid-sprint** | For the capacity screen |
| **Two members over-allocated** | The warning has to be visible |
| **2-3 unestimated tasks** | The "counted as zero" case |
| **Scope creep in the active sprint** | 2 tasks added on day 8, with worklogs before and after |
| **Daily worklogs across the sprint** | Burndown needs real daily rows, not two endpoints |

The last one is easy to forget and the burndown is meaningless without it.

**The seeder is not a fixture, it is the demo.** Time spent here shows up directly
in how the project reads.
