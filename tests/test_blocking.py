"""
Derived status — docs/TEST_PLAN.md §2.

A task is blocked if any dependency is not done. Never stored, never set by
a user, never updated by a signal — the property in core.models.Task simply
computes a different answer on the next read.
"""

import pytest

from core.models import Task, TaskDependency
from tests.factories import ProjectFactory, TaskFactory

pytestmark = pytest.mark.django_db


def make_tasks(*names, project=None):
    project = project or ProjectFactory()
    return [
        TaskFactory(project=project, number=i + 1, title=name)
        for i, name in enumerate(names)
    ]


def depend(task, depends_on):
    return TaskDependency.objects.create(task=task, depends_on=depends_on)


def test_task_with_no_dependencies_is_never_blocked():
    a = make_tasks("A")[0]

    assert a.is_blocked is False


def test_task_is_blocked_while_any_dependency_is_unfinished():
    a, b = make_tasks("A", "B")
    depend(b, a)

    assert b.is_blocked is True


def test_completing_the_last_dependency_unblocks_with_no_write():
    a, b = make_tasks("A", "B")
    depend(b, a)
    assert b.is_blocked is True

    b_before = Task.objects.get(pk=b.pk)

    a.state = Task.State.DONE
    a.save()

    b_after = Task.objects.get(pk=b.pk)
    assert b_after.is_blocked is False
    # The point: nothing touched B's row.
    assert b_after.created_at == b_before.created_at


def test_task_with_two_dependencies_needs_both_done():
    a, b, c = make_tasks("A", "B", "C")
    depend(c, a)
    depend(c, b)

    assert c.is_blocked is True

    a.state = Task.State.DONE
    a.save()
    assert c.is_blocked is True  # b still unfinished

    b.state = Task.State.DONE
    b.save()
    assert c.is_blocked is False


def test_reopening_a_dependency_reblocks_the_dependent():
    a, b = make_tasks("A", "B")
    depend(b, a)

    a.state = Task.State.DONE
    a.save()
    assert b.is_blocked is False

    a.state = Task.State.IN_PROGRESS
    a.save()
    assert b.is_blocked is True


def test_blocked_is_not_a_storable_state():
    values = [value for value, _label in Task.State.choices]
    assert "blocked" not in values


def test_deleting_a_dependency_unblocks():
    a, b = make_tasks("A", "B")
    dependency = depend(b, a)
    assert b.is_blocked is True

    dependency.delete()

    assert b.is_blocked is False
