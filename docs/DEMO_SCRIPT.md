# Demo Script

A four-minute walkthrough, screen by screen, with what to say. The screens
themselves are specified in [UI_FLOW.md](UI_FLOW.md).

---

## What makes a demo read as real

Every beginner demo looks the same: five tasks, nothing blocked, everyone at
exactly 40 hours. An interviewer recognises it immediately.

Real projects are **partly stuck at all times**. Some work is blocked. Someone is
overloaded. Someone is on leave. Two tasks got added mid-sprint because they
always do.

| Toy demo | Real demo |
|---|---|
| 5 tasks, all to do | 45 tasks across 3 columns, several blocked |
| Everyone at 40h | One at 52h, one at 16h on leave, two unestimated tasks |
| One sprint | 3 sprints — velocity needs history |
| Nothing blocked | A 4-deep chain and a diamond in the graph |
| Everything planned perfectly | **16 hours of scope creep on day 8** |
| Everything works | **One limitation you point out yourself** |

That last row is the strongest signal available. Someone hiding weaknesses does
not volunteer them.

---

## Before you start

- Seeder has been run: `python manage.py seed_demo`
- Browser open on the board
- **Confirm the cycle demo still reproduces** — the two tasks that trigger it must
  be the ones you plan to click. Check this after every seeder change.

---

## The script

### 1. Board — 20 seconds

Open on the board.

> "This is a sprint planning tool for a small team. Forty-five tasks, one active
> sprint."

Point at a greyed row with a lock.

> "These are blocked. But blocked is not a status anyone set — it is computed.
> A task is blocked if any dependency is not done, so nobody can forget to update
> it."

**Purpose:** plants the idea that state is derived before showing why that matters.

---

### 2. Cycle rejection — 60 seconds

**This is the core of the demo. Do not rush it.**

Open a task, click **Add dependency**, and pick the task that already depends on
it. Submit.

```
!  Circular dependency

   This would create a cycle:

     CAD-3 (API keys)
       -> CAD-7 (Payment gateway)
       -> CAD-3 (API keys)

   Neither task could ever start.
```

> "Before the dependency is saved, it walks the graph from the target to see
> whether it can reach the task being edited. If it can, the edge closes a loop —
> and those two tasks would wait on each other forever with nothing on screen
> saying so."

Then, the part that matters:

> "The hard case is not this one. It is making sure a **diamond** is still legal —
> A blocks B and C, and both block D. D is reachable from A two different ways,
> and a naive check calls that a cycle. Rejecting a legal diamond is the most
> likely bug in that function, so it has its own test."

And:

> "The error names the actual path because the path falls out of the search
> anyway. 'Invalid dependency' tells someone they are wrong; naming the loop tells
> them what to fix."

**Purpose:** this is the project. Sixty seconds here is worth more than the rest
combined.

**Likely interruption:** *"How does it scale?"* — Good. It is O(V+E) per insert on
graphs of a few hundred nodes, so microseconds. A transitive-closure table would
make reads faster and every write more complicated; not warranted at this size.
Being able to name the alternative and why it was not built is the answer.

---

### 3. Unblocking, live — 30 seconds

Go to the blocking task. Mark it **Done**. Return to the board.

The previously greyed task is now active. The lock is gone.

> "No update ran against that second task. Nothing wrote to it. The next read just
> computes a different answer, because the status is derived rather than stored."

> "If it were stored, it would need updating every time any dependency changed —
> and the first missed update gives you a tool that says 'ready' about something
> that is not."

**Purpose:** concrete proof of a design decision, in five seconds of clicking.

---

### 4. Capacity — 45 seconds

Open the capacity view.

```
Team: 187h allocated / 152h available     ! over capacity

Rahul Sharma   ####################====  52 / 40h   ! over
Priya Mehta    ######                    16 / 16h
               on leave 08-10 Sep (3 days)
Amit Kumar     ############              31 / 40h
               2 tasks unestimated
```

> "Everyone has forty hours in a two-week sprint. Priya's capacity is sixteen
> because she is on leave for three days — and only working days count, since a
> weekend inside a leave range was never capacity to begin with."

> "Amit has two unestimated tasks. They count as zero, and the screen says so.
> Treating unknown as zero silently understates his load; picking a default
> invents data. Showing it is the honest option."

Then the product point:

> "Over-allocation warns, it does not block. Managers overload people on purpose —
> a deadline, or a specialist nobody else can cover. A tool that refuses gets
> worked around within a day, and then it knows nothing."

**Purpose:** the last paragraph is product thinking, and it is what separates this
from an arithmetic exercise.

---

### 5. Burndown and scope creep — 40 seconds

Open the sprint page.

Point at the step up on day 8.

> "Sprint started with 152 committed hours. On day eight, sixteen more got added —
> the two tasks listed underneath."

> "When the sprint starts, every estimate is snapshotted. Anything without a
> snapshot row was added afterwards, and that is the entire definition of scope
> creep — there is no extra flag."

> "Without the snapshot the line would just flatten, and a team that took on
> sixteen extra hours would look identical to one that planned correctly. The
> burndown would quietly become fiction."

**Purpose:** shows a design decision whose whole purpose is honesty about the data.

---

### 6. Name your own limitation — 20 seconds

Do not skip this.

> "One thing I did not build: the graph walk runs on every dependency insert, which
> is fine at a few hundred tasks but would not be at a hundred thousand. The fix is
> a transitive-closure table — reads get faster, every write gets more complicated.
> I did not build it because I could not honestly test it at a scale where it
> matters, and building it anyway would have been guessing."

> "The other one is that `is_blocked` is computed per task, so the board would be
> N+1 without prefetching. There is a test asserting the query count, because that
> is exactly the kind of thing that comes back silently."

**Purpose:** volunteering an understood, documented limitation is the most credible
move in a demo — and it steers the conversation onto ground you have thought
about.

---

## Total: about 3 minutes 15 seconds

Leave room. Interruptions are the point.

---

## Questions that will come, and where the answer lives

| Question | Answer |
|---|---|
| "Why not store blocked as a status?" | TECHNICAL_SPEC §3 — drift, and a tool that lies |
| "How do you detect the cycle?" | DFS from the target; `seen` is what allows diamonds |
| "Does the diamond case work?" | Yes, and it has a dedicated test — TEST_PLAN §1 |
| "How would this scale?" | O(V+E) per insert; transitive closure is the alternative |
| "Why does over-allocation only warn?" | TECHNICAL_SPEC §4 — a tool that refuses gets bypassed |
| "What about unestimated tasks?" | Counted as zero, reported separately, deliberately |
| "Why snapshot the sprint?" | Estimates change; a burndown from current data is fiction |
| "Isn't this just Jira?" | Jira is a board. This answers whether a task *can* start and whether anyone has *room* — the two things a board does not |

---

## If the demo has to be two minutes

Cut to three moments:

1. **Cycle rejection** (60s) — the core
2. **Unblocking live** (30s) — derived state, proven in five seconds
3. **Your own limitation** (20s) — the credibility

Skip the board tour, capacity, and burndown. Those support the story; these three
are the story.
