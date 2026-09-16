# Test Plan

Every test to write, grouped by what it protects. Target: **~75 tests**, pytest.

The behaviour being pinned is specified in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md).

---

## The principle

Most of these are fast because the two hard parts — cycle detection and capacity
arithmetic — are plain functions over data. No mocking, no external services.

The three tests that carry the most weight:

1. **The diamond is allowed** — the case a naive implementation gets wrong.
2. **200 random edges, then an independent cycle check** — the graph invariant.
3. **A blocked task unblocks with no write** — proving derived status is derived.

---

## 1. Cycle detection — ~25 tests

`tests/test_dependency_graph.py`

No HTTP, no views. Build a graph, attempt an edge, assert.

### The cases that must be rejected

```python
def test_direct_cycle_is_rejected():
    a, b = task("A"), task("B")
    Dependency.objects.create(task=b, depends_on=a)      # B waits for A

    with pytest.raises(ValidationError, match="Circular"):
        Dependency.objects.create(task=a, depends_on=b)  # A waits for B
```

- `test_three_node_cycle_is_rejected` — A -> B -> C -> A
- `test_five_node_cycle_is_rejected` — depth is the point
- `test_self_dependency_is_rejected` — at the database level, via the CHECK constraint
- `test_cycle_through_a_long_chain_is_rejected` — 20 nodes, edge closes at the far end

### The cases that must be ALLOWED

**These matter more than the rejections.** A cycle detector that rejects
everything passes every test above.

```python
def test_diamond_is_allowed():
    # A -> B, A -> C, B -> D, C -> D
    # D is reachable from A by two routes. This is NOT a cycle.
    a, b, c, d = task("A"), task("B"), task("C"), task("D")
    Dependency.objects.create(task=b, depends_on=a)
    Dependency.objects.create(task=c, depends_on=a)
    Dependency.objects.create(task=d, depends_on=b)
    Dependency.objects.create(task=d, depends_on=c)   # must not raise

    assert d.dependencies.count() == 2
```

- `test_two_tasks_can_share_a_dependency` — fan-out
- `test_one_task_can_have_many_dependencies` — fan-in
- `test_parallel_chains_are_allowed` — A->B->C and D->E->F in one project
- `test_deep_linear_chain_is_allowed` — 50 nodes, no cycle
- `test_reconnecting_two_branches_is_allowed` — the diamond, one level deeper

### The error message

- `test_error_names_the_actual_cycle_path` — the message contains both task keys
- `test_error_mentions_neither_task_could_start`

### Enforcement points

- `test_cycle_is_rejected_in_the_admin` — `clean()` runs there too
- `test_cycle_is_rejected_via_the_form`
- `test_duplicate_edge_is_rejected` — the unique constraint

### The graph invariant

```python
def test_no_cycle_survives_random_graph_building():
    tasks = [task(f"T{i}") for i in range(30)]

    for _ in range(200):
        a, b = random.sample(tasks, 2)
        try:
            Dependency.objects.create(task=a, depends_on=b)
        except ValidationError:
            pass                      # rejected, as intended

    assert not graph_contains_cycle(tasks)   # independent checker, not the same code
```

The independent checker matters — asserting with the same function under test
proves only that it agrees with itself. Seed the randomness so a failure
reproduces.

---

## 2. Derived status — ~12 tests

`tests/test_blocking.py`

```python
def test_completing_the_last_dependency_unblocks_with_no_write():
    a, b = task("A"), task("B")
    Dependency.objects.create(task=b, depends_on=a)
    assert b.is_blocked

    a.state = "done"
    a.save()

    assert not b.is_blocked      # b was never written to
    assert b.updated_at == original_updated_at
```

The second assertion is the point: nothing touched B.

- `test_task_with_no_dependencies_is_never_blocked`
- `test_task_is_blocked_while_any_dependency_is_unfinished`
- `test_task_with_two_dependencies_needs_both_done`
- `test_reopening_a_dependency_reblocks_the_dependent`
- `test_blocked_is_not_a_storable_state` — assert `"blocked"` is not in `Task.STATE_CHOICES`
- `test_a_blocked_task_cannot_be_moved_to_in_progress`
- `test_deleting_a_dependency_unblocks`

---

## 3. Capacity — ~20 tests

`tests/test_capacity.py`

### Arithmetic

```python
def test_two_week_sprint_gives_eighty_hours():
    m = member(weekly_hours=40)
    s = sprint(starts_on="2026-09-01", ends_on="2026-09-14")
    assert capacity_for(m, s) == 80
```

- `test_one_week_sprint_gives_forty_hours`
- `test_part_time_member_scales_proportionally` — 20 weekly hours

### Time off

- `test_timeoff_inside_the_sprint_reduces_capacity`
- `test_weekend_inside_a_leave_range_does_not_reduce_capacity` — it was never capacity
- `test_timeoff_outside_the_sprint_does_not_reduce_capacity`
- `test_timeoff_partially_overlapping_the_sprint_reduces_only_the_overlap`
- `test_leave_covering_the_whole_sprint_gives_zero_capacity`

### Allocation

- `test_allocation_sums_assigned_unfinished_estimates`
- `test_completed_tasks_do_not_count_toward_allocation`
- `test_unassigned_tasks_count_toward_the_sprint_but_not_a_person`
- `test_unestimated_tasks_count_as_zero_and_are_reported_separately`

### Over-allocation

```python
def test_over_allocation_warns_but_does_not_block():
    m = member(weekly_hours=40)
    assign_hours(m, 52)

    assert m.is_over_allocated
    assign_task(m, task(estimate=8))     # must not raise
```

- `test_sprint_over_capacity_is_flagged` — 200 hours of work, 150 of capacity
- `test_capacity_is_frozen_at_sprint_start` — booking leave later does not rewrite it

---

## 4. Sprints and scope — ~15 tests

`tests/test_sprints.py`

### The snapshot

```python
def test_starting_a_sprint_snapshots_every_estimate():
    s = sprint_with_tasks(estimates=[3, 5, 8])
    s.start()

    assert s.commitments.count() == 3
    assert sum(c.estimate_hours_at_start for c in s.commitments.all()) == 16
```

- `test_re_estimating_after_start_does_not_change_the_commitment`
- `test_starting_a_sprint_is_atomic` — force a failure, assert no partial commitments
- `test_a_sprint_cannot_be_started_twice`

### Scope creep

```python
def test_a_task_added_after_start_is_scope_creep():
    s = started_sprint()
    t = task(estimate=8)
    s.add_task(t)

    assert t in s.scope_creep_tasks()
    assert s.committed_hours == 16
    assert s.added_hours == 8
```

- `test_a_task_removed_after_start_still_counts_as_committed`
- `test_scope_creep_is_the_absence_of_a_commitment_row` — no separate flag exists

### Burndown and velocity

- `test_worklog_written_daily_for_each_unfinished_task`
- `test_burndown_separates_committed_from_added`
- `test_velocity_uses_committed_hours_only`
- `test_velocity_needs_three_completed_sprints_before_it_reports`

---

## 5. Permissions — ~10 tests

`tests/test_permissions.py`

- `test_viewer_cannot_create_a_task`
- `test_contributor_cannot_start_a_sprint`
- `test_manager_can_start_a_sprint`
- `test_member_of_project_a_cannot_see_project_b_tasks` — expect **404**, not 403;
  403 confirms the object exists
- `test_every_view_uses_the_permission_mixin` — walk the URLconf and assert it, so
  a new unprotected view fails the suite rather than shipping

---

## 6. Query counts — ~3 tests

`tests/test_queries.py`

```python
def test_board_renders_in_constant_queries():
    project_with_tasks(45, with_dependencies=True)

    with assertNumQueries(4):
        client.get(f"/projects/{project.id}/board/")
```

Derived `is_blocked` makes N+1 the natural failure mode
([TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) §3). This test is what stops it returning
silently.

- `test_capacity_view_does_not_scale_queries_with_members`

---

## Running

```bash
pytest
pytest tests/test_dependency_graph.py    # the core
pytest -n auto
```

The graph suite must stay fast. If it slows, something has started hitting the
database inside the walk.
