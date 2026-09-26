# Testing

65 tests, pytest, against a real Postgres database. The whole suite runs in
about 40 seconds.

## Running them

```bash
docker compose exec web pytest
docker compose exec web pytest tests/test_dependency_graph.py -v
docker compose exec web pytest -n auto
```

Test dependencies live in `requirements-dev.txt`.

## Why Postgres, not SQLite

The suite runs against the same Postgres the app uses in development, not
an in-memory SQLite swap. Several things being tested don't exist on
SQLite: the `UNIQUE`/`CHECK` constraints on `TaskDependency` that enforce
the no-self-dependency and no-duplicate-edge rules at the database level,
and `assertNumQueries`'s query-count assertions, which depend on Postgres's
actual query planning rather than SQLite's.

## What is covered

| File | Focus |
|---|---|
| `test_dependency_graph.py` | Cycle rejection (direct, 3-node, 5-node, self, long chain), the diamond and other legal cases, the error path, admin/form enforcement, a 200-edge random-graph invariant checked by an independent DFS |
| `test_blocking.py` | `is_blocked` as derived state — unblocking with zero writes to the dependent, reblocking, deletion |
| `test_capacity.py` | Weekly-hours scaling, time-off overlap (including partial and weekend-only cases), allocation, unestimated tasks, over-allocation, the frozen snapshot |
| `test_sprints.py` | `Sprint.start()` atomicity, scope creep as absence of a commitment row, burndown series, velocity |
| `test_permissions.py` | Role checks, HTTP 404-not-403 for non-members, a URLconf walk asserting every project-scoped view uses the permission mixin |
| `test_queries.py` | Board and capacity views run in a constant number of queries regardless of task/member count |

## The three tests that carry the most weight

1. **`test_diamond_is_allowed`** — the case a naive cycle detector gets
   wrong. A detector that rejects every edge passes every rejection test;
   only this one catches that.
2. **`test_no_cycle_survives_random_graph_building`** — 200 random edges
   against a 30-node graph, then checked by a second, independently
   written cycle checker. Seeded, so a failure reproduces.
3. **`test_completing_the_last_dependency_unblocks_with_no_write`** —
   proves derived status is actually derived, not just usually correct.

## Query-count tests, and why they exist

`is_blocked` makes N+1 the natural failure mode for any list of tasks —
and it happened twice during development despite `prefetch_related` being
in place: the property's own query ignored the prefetch cache, and a
missing `select_related("project")` meant `task.key` lazy-loaded it once
per task. Both are fixed, and `test_queries.py` pins the board and
capacity views at a constant query count so either regression fails the
suite immediately rather than showing up as a slow page once real data
accumulates.

## Known gaps

- No browser-level (Selenium/Playwright) tests — the HTMX add-dependency
  flow is tested at the Django test-client level (a real POST, a real
  `ValidationError`, a real rendered partial), not by driving an actual
  browser.
- No load/concurrency tests for the dependency graph. Two users adding
  conflicting edges to the same project at once is a known, accepted gap
  (see [architecture.md](architecture.md)'s "known limits").
