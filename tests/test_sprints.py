"""
Sprints and scope — docs/TEST_PLAN.md §4.

Starting a sprint freezes scope (SprintCommitment + Capacity, in one
transaction). Scope creep is the absence of a commitment row, not a flag.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from sprints.models import Capacity, Sprint, SprintCommitment, WorkLog
from sprints.services import (
    SprintAlreadyStartedError,
    velocity,
    write_daily_worklogs,
)
from tasks.models import Task
from tests.factories import MemberFactory, ProjectFactory, SprintFactory, TaskFactory

pytestmark = pytest.mark.django_db


def sprint_with_tasks(estimates, project=None):
    project = project or ProjectFactory()
    sprint = SprintFactory(
        project=project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14)
    )
    # number is unique per project, not per sprint, so tasks across sprints
    # in the same project must not collide.
    existing = Task.objects.filter(project=project).count()
    tasks = [
        TaskFactory(project=project, sprint=sprint, number=existing + i + 1, estimate_hours=e)
        for i, e in enumerate(estimates)
    ]
    return sprint, tasks


# ---------------------------------------------------------------------------
# The snapshot
# ---------------------------------------------------------------------------


def test_starting_a_sprint_snapshots_every_estimate():
    sprint, _tasks = sprint_with_tasks([3, 5, 8])

    sprint.start()

    assert sprint.commitments.count() == 3
    assert sum(c.estimate_hours_at_start for c in sprint.commitments.all()) == 16


def test_starting_a_sprint_stamps_state_and_started_at():
    sprint, _tasks = sprint_with_tasks([3])

    sprint.start()

    assert sprint.state == Sprint.State.ACTIVE
    assert sprint.started_at is not None


def test_starting_a_sprint_snapshots_capacity_for_every_member():
    project = ProjectFactory()
    m1 = MemberFactory(project=project, weekly_hours=40)
    m2 = MemberFactory(project=project, weekly_hours=20)
    sprint = SprintFactory(project=project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14))

    sprint.start()

    assert Capacity.objects.filter(sprint=sprint, member=m1).exists()
    assert Capacity.objects.filter(sprint=sprint, member=m2).exists()
    assert Capacity.objects.get(sprint=sprint, member=m1).available_hours == Decimal(80)


def test_re_estimating_after_start_does_not_change_the_commitment():
    sprint, tasks = sprint_with_tasks([5])
    sprint.start()

    task = tasks[0]
    task.estimate_hours = 20
    task.save()

    commitment = SprintCommitment.objects.get(sprint=sprint, task=task)
    assert commitment.estimate_hours_at_start == Decimal(5)


def test_starting_a_sprint_is_atomic():
    sprint, tasks = sprint_with_tasks([3, 5])

    # Force a failure partway through by pre-creating a conflicting
    # commitment row for one of the two tasks, so the unique constraint
    # trips inside the transaction.
    SprintCommitment.objects.create(
        sprint=sprint, task=tasks[0], estimate_hours_at_start=Decimal(3)
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            sprint.start()

    # No partial commitments beyond the one that already existed, and the
    # sprint was never flipped to active.
    sprint.refresh_from_db()
    assert sprint.state == Sprint.State.PLANNED
    assert sprint.commitments.count() == 1


def test_a_sprint_cannot_be_started_twice():
    sprint, _tasks = sprint_with_tasks([3])
    sprint.start()

    with pytest.raises(SprintAlreadyStartedError):
        sprint.start()


# ---------------------------------------------------------------------------
# Scope creep
# ---------------------------------------------------------------------------


def test_a_task_added_after_start_is_scope_creep():
    sprint, _tasks = sprint_with_tasks([3, 5])
    sprint.start()

    new_task = TaskFactory(project=sprint.project, number=99, estimate_hours=8)
    sprint.add_task(new_task)

    assert new_task in sprint.scope_creep_tasks()
    assert sprint.committed_hours == Decimal(8)
    assert sprint.added_hours == Decimal(8)


def test_a_task_removed_after_start_still_counts_as_committed():
    sprint, tasks = sprint_with_tasks([3, 5])
    sprint.start()

    removed = tasks[0]
    removed.sprint = None
    removed.save(update_fields=["sprint"])

    # The commitment row survives even though the task left the sprint.
    assert SprintCommitment.objects.filter(sprint=sprint, task=removed).exists()
    assert sprint.committed_hours == Decimal(8)  # 3 + 5, unchanged


def test_scope_creep_is_the_absence_of_a_commitment_row():
    sprint, _tasks = sprint_with_tasks([3])
    sprint.start()

    new_task = TaskFactory(project=sprint.project, number=99, estimate_hours=8)
    sprint.add_task(new_task)

    # No dedicated flag anywhere on Task or SprintCommitment — just missing rows.
    assert not SprintCommitment.objects.filter(sprint=sprint, task=new_task).exists()
    assert list(sprint.scope_creep_tasks()) == [new_task]


# ---------------------------------------------------------------------------
# Burndown and velocity
# ---------------------------------------------------------------------------


def test_worklog_written_daily_for_each_unfinished_task():
    sprint, tasks = sprint_with_tasks([3, 5])
    tasks[1].state = Task.State.DONE
    tasks[1].save()

    written = write_daily_worklogs(sprint, as_of=date(2026, 9, 2))

    assert len(written) == 1  # the done task is skipped
    log = WorkLog.objects.get(task=tasks[0], date=date(2026, 9, 2))
    assert log.remaining_hours == Decimal(3)


def test_burndown_separates_committed_from_added():
    sprint, _tasks = sprint_with_tasks([3, 5])
    sprint.start()

    new_task = TaskFactory(project=sprint.project, number=99, estimate_hours=8)
    sprint.add_task(new_task)

    assert sprint.committed_hours == Decimal(8)
    assert sprint.added_hours == Decimal(8)
    # The two series never merge into one number silently.
    assert sprint.committed_hours != sprint.committed_hours + sprint.added_hours


def test_velocity_uses_committed_hours_only():
    project = ProjectFactory()
    completed = []
    for i in range(3):
        sprint, _tasks = sprint_with_tasks([10], project=project)
        sprint.start()
        new_task = TaskFactory(project=project, number=100 + i, estimate_hours=99)
        sprint.add_task(new_task)  # scope creep — must not affect velocity
        sprint.state = Sprint.State.COMPLETED
        sprint.started_at = sprint.started_at or None
        sprint.save()
        completed.append(sprint)

    assert velocity(project) == Decimal(10)


def test_velocity_needs_three_completed_sprints_before_it_reports():
    project = ProjectFactory()
    for _ in range(2):
        sprint, _tasks = sprint_with_tasks([10], project=project)
        sprint.start()
        sprint.state = Sprint.State.COMPLETED
        sprint.save()

    assert velocity(project) is None
