"""
Cycle detection — docs/TEST_PLAN.md §1.

No HTTP, no views. Build a graph, attempt an edge, assert.

The cases that must be ALLOWED matter more than the cases that must be
rejected — a detector that rejects everything passes every rejection test.
"""

import random

import pytest
from django.core.exceptions import ValidationError
from django.forms import modelform_factory

from tasks.models import Task, TaskDependency
from tests.factories import ProjectFactory, TaskDependencyFactory, TaskFactory

pytestmark = pytest.mark.django_db


def make_tasks(*names, project=None):
    """Create one Task per name, all in the same project unless given one."""
    project = project or ProjectFactory()
    return [
        TaskFactory(project=project, number=i + 1, title=name)
        for i, name in enumerate(names)
    ]


def depend(task, depends_on):
    return TaskDependency.objects.create(task=task, depends_on=depends_on)


# ---------------------------------------------------------------------------
# Cases that must be REJECTED
# ---------------------------------------------------------------------------


def test_direct_cycle_is_rejected():
    a, b = make_tasks("A", "B")
    depend(b, a)  # B waits for A

    with pytest.raises(ValidationError, match="Circular"):
        depend(a, b)  # A waits for B


def test_three_node_cycle_is_rejected():
    a, b, c = make_tasks("A", "B", "C")
    depend(b, a)
    depend(c, b)

    with pytest.raises(ValidationError, match="Circular"):
        depend(a, c)  # A -> C -> B -> A


def test_five_node_cycle_is_rejected():
    a, b, c, d, e = make_tasks("A", "B", "C", "D", "E")
    depend(b, a)
    depend(c, b)
    depend(d, c)
    depend(e, d)

    with pytest.raises(ValidationError, match="Circular"):
        depend(a, e)  # closes A -> E -> D -> C -> B -> A


def test_self_dependency_is_rejected():
    a = make_tasks("A")[0]

    with pytest.raises(ValidationError):
        depend(a, a)


def test_cycle_through_a_long_chain_is_rejected():
    tasks = make_tasks(*[f"T{i}" for i in range(20)])
    for i in range(1, 20):
        depend(tasks[i], tasks[i - 1])  # T1->T0, T2->T1, ... T19->T18

    with pytest.raises(ValidationError, match="Circular"):
        depend(tasks[0], tasks[19])  # closes the loop at the far end


# ---------------------------------------------------------------------------
# Cases that must be ALLOWED
# ---------------------------------------------------------------------------


def test_diamond_is_allowed():
    # A -> B, A -> C, B -> D, C -> D
    # D is reachable from A by two routes. This is NOT a cycle.
    a, b, c, d = make_tasks("A", "B", "C", "D")
    depend(b, a)
    depend(c, a)
    depend(d, b)
    depend(d, c)  # must not raise

    assert d.dependencies.count() == 2


def test_two_tasks_can_share_a_dependency():
    # fan-out: B and C both depend on A
    a, b, c = make_tasks("A", "B", "C")
    depend(b, a)
    depend(c, a)  # must not raise

    assert a.dependents.count() == 2


def test_one_task_can_have_many_dependencies():
    # fan-in: D depends on A, B and C
    a, b, c, d = make_tasks("A", "B", "C", "D")
    depend(d, a)
    depend(d, b)
    depend(d, c)  # must not raise

    assert d.dependencies.count() == 3


def test_parallel_chains_are_allowed():
    # A->B->C and D->E->F in one project, no relation between the two chains
    a, b, c, d, e, f = make_tasks("A", "B", "C", "D", "E", "F")
    depend(b, a)
    depend(c, b)
    depend(e, d)
    depend(f, e)  # must not raise

    assert c.dependencies.count() == 1
    assert f.dependencies.count() == 1


def test_deep_linear_chain_is_allowed():
    tasks = make_tasks(*[f"T{i}" for i in range(50)])
    for i in range(1, 50):
        depend(tasks[i], tasks[i - 1])  # must not raise

    assert tasks[49].dependencies.count() == 1


def test_reconnecting_two_branches_is_allowed():
    # The diamond, one level deeper: A->B->D, A->C->E, D->F, E->F
    a, b, c, d, e, f = make_tasks("A", "B", "C", "D", "E", "F")
    depend(b, a)
    depend(c, a)
    depend(d, b)
    depend(e, c)
    depend(f, d)
    depend(f, e)  # must not raise

    assert f.dependencies.count() == 2


# ---------------------------------------------------------------------------
# The error message
# ---------------------------------------------------------------------------


def test_error_names_the_actual_cycle_path():
    project = ProjectFactory(key="CAD")
    a, b = make_tasks("API keys", "Payment gateway", project=project)
    depend(b, a)  # Payment gateway waits for API keys

    with pytest.raises(ValidationError) as excinfo:
        depend(a, b)  # API keys waits for Payment gateway

    message = str(excinfo.value)
    assert a.key in message
    assert b.key in message


def test_error_mentions_neither_task_could_start():
    a, b = make_tasks("A", "B")
    depend(b, a)

    with pytest.raises(ValidationError, match="Neither task could ever start"):
        depend(a, b)


# ---------------------------------------------------------------------------
# Enforcement points
# ---------------------------------------------------------------------------


def test_cycle_is_rejected_in_the_admin():
    # clean() runs regardless of caller — exercise it the way ModelAdmin does,
    # via full_clean(), rather than standing up the admin site itself.
    a, b = make_tasks("A", "B")
    depend(b, a)

    dependency = TaskDependency(task=a, depends_on=b)
    with pytest.raises(ValidationError, match="Circular"):
        dependency.full_clean()


def test_cycle_is_rejected_via_the_form():
    a, b = make_tasks("A", "B")
    depend(b, a)

    TaskDependencyForm = modelform_factory(TaskDependency, fields=["task", "depends_on"])
    form = TaskDependencyForm(data={"task": a.pk, "depends_on": b.pk})

    assert not form.is_valid()
    assert "Circular" in str(form.errors)


def test_duplicate_edge_is_rejected():
    a, b = make_tasks("A", "B")
    depend(b, a)

    with pytest.raises(Exception):
        TaskDependency.objects.create(task=b, depends_on=a)


# ---------------------------------------------------------------------------
# The graph invariant
# ---------------------------------------------------------------------------


def graph_contains_cycle(tasks):
    """
    Independent cycle checker (plain DFS over dicts), deliberately not
    sharing code with tasks.services.would_create_cycle — asserting with the
    same function under test would only prove it agrees with itself.
    """
    edges = {t.pk: set() for t in tasks}
    for t in tasks:
        for dep in TaskDependency.objects.filter(task=t).values_list("depends_on_id", flat=True):
            edges[t.pk].add(dep)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t.pk: WHITE for t in tasks}

    def visit(node):
        color[node] = GRAY
        for neighbor in edges[node]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and visit(neighbor):
                return True
        color[node] = BLACK
        return False

    return any(color[t.pk] == WHITE and visit(t.pk) for t in tasks)


def test_no_cycle_survives_random_graph_building():
    random.seed(1234)  # reproducible on failure

    tasks = make_tasks(*[f"T{i}" for i in range(30)])

    for _ in range(200):
        a, b = random.sample(tasks, 2)
        try:
            depend(a, b)
        except ValidationError:
            pass  # rejected, as intended
        except Exception:
            pass  # duplicate edge, also fine to skip

    assert not graph_contains_cycle(tasks)
