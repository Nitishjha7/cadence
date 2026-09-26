"""
Capacity — docs/testing.md.

available_hours = weekly_hours * (sprint_days / 7) - timeoff_hours
allocated_hours = sum(estimate_hours for assigned, unfinished tasks)

Over-allocation warns, it never blocks.
"""

from datetime import date
from decimal import Decimal

import pytest

from sprints.models import Capacity
from sprints.services import (
    allocated_hours_for,
    capacity_for,
    is_over_allocated,
    unestimated_task_count_for,
)
from tasks.models import Task
from tests.factories import MemberFactory, SprintFactory, TaskFactory, TimeOffFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


def test_two_week_sprint_gives_eighty_hours():
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14))

    assert capacity_for(m, s) == Decimal(80)


def test_one_week_sprint_gives_forty_hours():
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 7))

    assert capacity_for(m, s) == Decimal(40)


def test_part_time_member_scales_proportionally():
    m = MemberFactory(weekly_hours=20)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14))

    assert capacity_for(m, s) == Decimal(40)


# ---------------------------------------------------------------------------
# Time off
# ---------------------------------------------------------------------------


def test_timeoff_inside_the_sprint_reduces_capacity():
    # Sprint: Tue 2026-09-01 .. Mon 2026-09-14 (two weeks)
    # Leave: Mon 2026-09-07 .. Tue 2026-09-08 (2 working days)
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14))
    TimeOffFactory(member=m, starts_on=date(2026, 9, 7), ends_on=date(2026, 9, 8))

    assert capacity_for(m, s) == Decimal(80) - Decimal(16)  # 2 days * 8h


def test_weekend_inside_a_leave_range_does_not_reduce_capacity():
    # Leave: Sat 2026-09-05 .. Sun 2026-09-06 — both weekend days.
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14))
    TimeOffFactory(member=m, starts_on=date(2026, 9, 5), ends_on=date(2026, 9, 6))

    assert capacity_for(m, s) == Decimal(80)  # nothing was ever capacity here


def test_timeoff_outside_the_sprint_does_not_reduce_capacity():
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14))
    TimeOffFactory(member=m, starts_on=date(2026, 10, 1), ends_on=date(2026, 10, 5))

    assert capacity_for(m, s) == Decimal(80)


def test_timeoff_partially_overlapping_the_sprint_reduces_only_the_overlap():
    # Sprint: Tue 2026-09-01 .. Mon 2026-09-14
    # Leave starts before the sprint and ends inside it:
    # Thu 2026-08-27 .. Wed 2026-09-02 -> overlap is Tue 09-01, Wed 09-02 (2 working days)
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14))
    TimeOffFactory(member=m, starts_on=date(2026, 8, 27), ends_on=date(2026, 9, 2))

    assert capacity_for(m, s) == Decimal(80) - Decimal(16)  # 2 overlapping working days


def test_leave_covering_the_whole_sprint_gives_zero_capacity():
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 7))
    TimeOffFactory(member=m, starts_on=date(2026, 8, 25), ends_on=date(2026, 9, 10))

    assert capacity_for(m, s) == Decimal(0)


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def test_allocation_sums_assigned_unfinished_estimates():
    m = MemberFactory()
    s = SprintFactory(project=m.project)
    TaskFactory(project=m.project, sprint=s, assignee=m, estimate_hours=5, number=1)
    TaskFactory(project=m.project, sprint=s, assignee=m, estimate_hours=3, number=2)

    assert allocated_hours_for(m, s) == Decimal(8)


def test_completed_tasks_do_not_count_toward_allocation():
    m = MemberFactory()
    s = SprintFactory(project=m.project)
    TaskFactory(
        project=m.project, sprint=s, assignee=m, estimate_hours=5,
        state=Task.State.DONE, number=1,
    )

    assert allocated_hours_for(m, s) == Decimal(0)


def test_unassigned_tasks_count_toward_the_sprint_but_not_a_person():
    m = MemberFactory()
    s = SprintFactory(project=m.project)
    TaskFactory(project=m.project, sprint=s, assignee=None, estimate_hours=5, number=1)

    assert allocated_hours_for(m, s) == Decimal(0)


def test_unestimated_tasks_count_as_zero_and_are_reported_separately():
    m = MemberFactory()
    s = SprintFactory(project=m.project)
    TaskFactory(project=m.project, sprint=s, assignee=m, estimate_hours=None, number=1)
    TaskFactory(project=m.project, sprint=s, assignee=m, estimate_hours=None, number=2)
    TaskFactory(project=m.project, sprint=s, assignee=m, estimate_hours=4, number=3)

    assert allocated_hours_for(m, s) == Decimal(4)
    assert unestimated_task_count_for(m, s) == 2


# ---------------------------------------------------------------------------
# Over-allocation
# ---------------------------------------------------------------------------


def test_over_allocation_warns_but_does_not_block():
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 7))
    TaskFactory(project=m.project, sprint=s, assignee=m, estimate_hours=52, number=1)

    assert is_over_allocated(m, s) is True

    # must not raise
    TaskFactory(project=m.project, sprint=s, assignee=m, estimate_hours=8, number=2)
    assert allocated_hours_for(m, s) == Decimal(60)


def test_sprint_over_capacity_is_flagged():
    # 200 hours of work against 150 hours of team capacity (one-week sprint,
    # weekly_hours doubling as sprint capacity: 4 members at 37.5h/week).
    project = MemberFactory().project
    project_members = [MemberFactory(project=project, weekly_hours=38) for _ in range(3)]
    project_members.append(MemberFactory(project=project, weekly_hours=36))
    s = SprintFactory(project=project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 7))

    total_capacity = sum(capacity_for(m, s) for m in project_members)
    assert total_capacity == Decimal(150)

    for i, m in enumerate(project_members):
        TaskFactory(project=m.project, sprint=s, assignee=m, estimate_hours=50, number=i + 1)

    total_allocated = sum(allocated_hours_for(m, s) for m in project_members)
    assert total_allocated == Decimal(200)
    assert total_allocated > total_capacity


def test_capacity_is_frozen_at_sprint_start():
    # Booking leave *after* the sprint starts must not rewrite the snapshot
    # taken at start — Sprint.start() (Phase 4) is what makes this testable.
    m = MemberFactory(weekly_hours=40)
    s = SprintFactory(project=m.project, starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 14))

    s.start()
    frozen = Capacity.objects.get(sprint=s, member=m).available_hours
    assert frozen == Decimal(80)

    TimeOffFactory(member=m, starts_on=date(2026, 9, 8), ends_on=date(2026, 9, 9))

    # The live calculation now reflects the new leave...
    assert capacity_for(m, s) == Decimal(80) - Decimal(16)
    # ...but the frozen snapshot from sprint start does not.
    still_frozen = Capacity.objects.get(sprint=s, member=m).available_hours
    assert still_frozen == Decimal(80)
