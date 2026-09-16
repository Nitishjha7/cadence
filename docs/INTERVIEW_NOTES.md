# Interview Notes

Pitch, trade-offs, limitations, and the questions that will come.

Read a question, answer it **without looking**. Wherever you stall is where an
interviewer will push.

---

## 1. The 30-second pitch

> "It is a sprint planning tool, but built around the two questions a board does
> not answer: can this task even be started, and does the person it is assigned to
> have room?
>
> The first one is a graph problem — tasks depend on each other, and if someone
> creates a circular dependency those tasks wait on each other forever with
> nothing on screen saying so. So dependencies are validated with a depth-first
> search before the write, and the error names the actual loop.
>
> The second is arithmetic — capacity per person, minus leave, against assigned
> estimates. And sprint scope is snapshotted at start, so work added mid-sprint
> shows up as scope creep instead of silently flattening the burndown."

**Do not call it a Jira clone or a ticketing system.** Both invite the wrong
comparison, and "ticketing" collides with an unrelated project in my portfolio.
Say *sprint planning and capacity*.

---

## 2. Why this project

> "My portfolio was all Python web APIs and agentic work, with no Django project —
> and I was applying for Django roles, which is a screening problem before it is
> anything else.
>
> I picked this because it is the kind of thing Django is actually used for —
> server-rendered pages, auth and roles, admin as a back-office console — and
> because I could put a real algorithm at the centre instead of building another
> CRUD app."

Honest, and honesty about the portfolio gap reads better than a manufactured
origin story.

---

## 3. The three things worth defending

### Cycle detection

**Q: How does it work?**

Before saving `dependency(task=X, depends_on=Y)`, walk forward from Y. If X is
reachable, the new edge closes a loop. Iterative DFS, not recursive — a deep chain
would risk the recursion limit and the iterative form reads no worse.

**Q: What is the hard part?**

Not the cycles. The **diamond**: A blocks B and C, both block D. D is reachable
from A by two routes, and a naive implementation treats the second visit as a
revisit and calls it a cycle. Rejecting a legal diamond is the most likely bug in
that function, so it has a dedicated test — and so does a random-graph invariant
test that builds 200 edges and then checks the result with an *independent*
cycle checker, because asserting with the function under test only proves it
agrees with itself.

**Q: Where does the validation live?**

`TaskDependency.clean()`, so it applies to the admin, forms and the API. Putting
it in a view would leave the admin able to create a cycle — and the admin is the
manager console.

**Q: How would it scale?**

O(V+E) per insert. On a few hundred tasks that is microseconds. At a hundred
thousand you would keep a transitive-closure table — reads get faster, every write
gets more complicated. I did not build it because I could not honestly test it at
a scale where it matters.

### Derived status

**Q: Why not store `blocked` as a state?**

A stored flag has to be updated whenever any dependency changes state. The first
missed update produces a task that says "ready" when it is not — and a planning
tool that lies about readiness is worse than no tool.

Derived, completing the last dependency unblocks the dependent with **no write at
all**. The next read simply computes a different answer. There is a test asserting
the dependent row was never touched.

**Q: What does that cost?**

An N+1 on the board — one query per task to check its dependencies.
`prefetch_related` reduces it to a constant, and a query-count test pins it, so
the N+1 cannot return silently.

### Sprint snapshot

**Q: Why snapshot estimates at sprint start?**

Because estimates change during a sprint. A burndown computed from current
estimates shows a sprint that was never planned.

With the snapshot, scope creep has a definition that needs no extra flag: a task
in an active sprint with no commitment row was added afterwards. The burndown then
renders committed and added work separately, so a team that took on sixteen extra
hours does not look identical to one that planned correctly.

---

## 4. Known limitations — say these before you are asked

### The graph walk runs on every insert

Fine at a few hundred tasks, not at a hundred thousand. The alternative —
transitive closure — was not built because it could not be honestly tested at a
scale where it matters, and building it anyway would have been guessing.

### `is_blocked` is computed per task

Which makes N+1 the natural failure mode on any list view. Handled with
`prefetch_related` and pinned by a query-count test. Named here because it is a
real cost of a deliberate decision, not a hidden one.

### Unestimated tasks count as zero

They are reported separately in the UI rather than hidden. Treating unknown as
zero understates load; inventing a default invents data. Showing it is the honest
option, but it does mean the allocation number is an underestimate whenever the
count is non-zero.

### Capacity assumes uniform working days

Eight hours a day, weekends off, no partial days, no holiday calendar. Real teams
lose time to meetings. This is a simplification, stated in the README rather than
hidden behind a plausible-looking number.

---

## 5. Questions that will come

**Q: Isn't this just Jira?**

Jira is a board — create a card, move it, change status. That is CRUD. This
answers two things a board does not: whether a task *can* start, and whether
anyone has *room*. Those are a graph problem and an arithmetic problem, and they
are the whole project.

**Q: Why does over-allocation only warn?**

Because managers overload people on purpose — a deadline, or a specialist nobody
else can cover. A tool that refuses gets worked around within a day, and then it
knows nothing about what is actually happening. Warning keeps the data honest.

**Q: Why Django templates and HTMX instead of React?**

Because it is a back-office tool, and the rest of my portfolio is already API plus
React. Server-rendered forms with validation are what Django is for, and the
cycle-rejection flow — server validates, returns an error naming the path —
is the simplest possible thing this way rather than a state-sync problem.

**Q: How do you know the graph logic is right?**

Beyond the case tests, there is an invariant test: 200 random edges attempted
across 30 tasks, rejections allowed to fail, and then an independent checker
confirms no cycle exists. Seeded, so failures reproduce.

**Q: What happens if two people add dependencies at the same time?**

Both validate against the graph as it was, and either could pass a check the other
invalidates. At this scale the window is tiny and the failure is recoverable —
somebody deletes an edge. Closing it properly means serialising dependency writes
per project, which I would do with a row lock on the project if this were handling
real concurrency.

That question is worth answering honestly rather than claiming it is handled.

**Q: Why is the sprint start a transaction?**

It writes commitments for every task and capacity for every member. A partial
sprint start — some commitments, no capacity — would be a sprint that can never
produce a correct burndown, and there would be no obvious signal that it happened.

**Q: What would you build next?**

Holiday calendars in capacity, since "uniform working days" is the weakest
assumption in there. Then dependency-aware scheduling — given the graph and
capacity, suggest an order — which is the natural thing to build once both halves
exist.

---

## 6. If they ask about AI assistance

Answer plainly. Everyone uses it; what matters is whether you understand what came
out.

> "I used it the way I use documentation — to move faster. The decisions are mine
> and they are written down in DECISIONS.md as I made them: why blocked is derived
> rather than stored, why over-allocation warns instead of blocking, why the
> sprint snapshot exists. If you point at any line in the cycle detection I can
> tell you why it is that way and what breaks if you change it."

Then offer to do exactly that — the offer is the proof.

---

## 7. The one-line summary

> "The interesting part is not that it tracks tasks. It is that it can tell you a
> task **cannot be started**, and that the person you just assigned it to has no
> room for it."
