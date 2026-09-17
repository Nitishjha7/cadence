"""
Capacity arithmetic — kept out of models.py so it stays independently
testable and the models themselves stay thin records of fields.

See docs/TECHNICAL_SPEC.md §4 for the full write-up.
"""

from datetime import timedelta
from decimal import Decimal


def _date_range(starts_on, ends_on):
    """Every date from starts_on to ends_on, inclusive."""
    days = (ends_on - starts_on).days
    for offset in range(days + 1):
        yield starts_on + timedelta(days=offset)


def _working_days(starts_on, ends_on):
    """Count of Mon-Fri dates in the inclusive range."""
    return sum(1 for d in _date_range(starts_on, ends_on) if d.weekday() < 5)


def sprint_length_days(sprint):
    """Calendar days in the sprint, inclusive of both ends."""
    return (sprint.ends_on - sprint.starts_on).days + 1


def timeoff_hours_for(member, sprint):
    """
    Working days (Mon-Fri) of this member's leave that fall inside the
    sprint window, converted to hours at a standard 8h/day.

    A weekend inside a leave range is not capacity that was lost, because it
    was never capacity — so only the weekday overlap counts, not the leave
    range's own length.
    """
    total_days = 0
    for time_off in member.time_off.all():
        overlap_start = max(time_off.starts_on, sprint.starts_on)
        overlap_end = min(time_off.ends_on, sprint.ends_on)
        if overlap_start > overlap_end:
            continue  # no overlap with the sprint window
        total_days += _working_days(overlap_start, overlap_end)

    return Decimal(total_days) * Decimal(8)


def capacity_for(member, sprint):
    """
    available_hours = weekly_hours * (sprint_days / 7) - timeoff_hours

    Not stored — this is the live calculation. Sprint.start() (Phase 4)
    calls this once and freezes the result into a Capacity row; querying it
    afterwards should read that row, not recompute it, since leave booked
    after the sprint starts must not retroactively change what was
    committed to.
    """
    days = sprint_length_days(sprint)
    scaled = Decimal(member.weekly_hours) * Decimal(days) / Decimal(7)
    return scaled - timeoff_hours_for(member, sprint)


def allocated_hours_for(member, sprint):
    """
    Sum of estimate_hours for tasks assigned to this member, in this
    sprint, that are not yet done. Unestimated tasks count as zero — the
    caller is responsible for surfacing the unestimated count separately
    (docs/TECHNICAL_SPEC.md §4); silently defaulting to some other number
    would invent data.
    """
    from tasks.models import Task

    tasks = member.assigned_tasks.filter(sprint=sprint).exclude(state=Task.State.DONE)
    total = Decimal(0)
    for task in tasks:
        if task.estimate_hours is not None:
            total += task.estimate_hours
    return total


def unestimated_task_count_for(member, sprint):
    from tasks.models import Task

    return (
        member.assigned_tasks.filter(sprint=sprint)
        .exclude(state=Task.State.DONE)
        .filter(estimate_hours__isnull=True)
        .count()
    )


def is_over_allocated(member, sprint):
    """
    Flags, never blocks — docs/TECHNICAL_SPEC.md §4. Managers legitimately
    overload people; this is information, not a gate.
    """
    return allocated_hours_for(member, sprint) > capacity_for(member, sprint)
