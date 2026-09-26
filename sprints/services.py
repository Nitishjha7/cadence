"""
Capacity arithmetic and sprint lifecycle — kept out of models.py so it stays
independently testable and the models themselves stay thin records of
fields.

See docs/TECHNICAL_SPEC.md §4 and §5 for the full write-up.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


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


# ---------------------------------------------------------------------------
# Sprint lifecycle — docs/TECHNICAL_SPEC.md §5
# ---------------------------------------------------------------------------


class SprintAlreadyStartedError(Exception):
    """Raised by start_sprint() on a sprint that is not `planned`."""


@transaction.atomic
def start_sprint(sprint, *, now=None):
    """
    Transition planned -> active. In one transaction:

    1. Write a SprintCommitment row for every task currently in the sprint,
       copying the current estimate.
    2. Compute and store Capacity for every project member.
    3. Stamp started_at.

    Both snapshots are taken now, not computed later, because both inputs
    change during a sprint — estimates get revised, leave gets booked. A
    burndown computed from today's numbers would show a sprint that was
    never planned. @transaction.atomic means a failure partway through
    (e.g. a duplicate commitment) leaves no partial commitments behind.
    """
    from sprints.models import Capacity, Sprint, SprintCommitment

    if sprint.state != Sprint.State.PLANNED:
        raise SprintAlreadyStartedError(
            f"Sprint {sprint.name!r} is {sprint.state}, not planned — it cannot be started again."
        )

    for task in sprint.tasks.all():
        SprintCommitment.objects.create(
            sprint=sprint, task=task, estimate_hours_at_start=task.estimate_hours
        )

    for member in sprint.project.members.all():
        Capacity.objects.create(
            member=member, sprint=sprint, available_hours=capacity_for(member, sprint)
        )

    sprint.state = Sprint.State.ACTIVE
    sprint.started_at = now or timezone.now()
    sprint.save(update_fields=["state", "started_at"])

    return sprint


def add_task_to_sprint(sprint, task):
    """
    Add a task to an already-active sprint. No SprintCommitment row is
    written — that absence *is* the scope-creep marker
    (docs/TECHNICAL_SPEC.md §5), not a separate flag.
    """
    task.sprint = sprint
    task.save(update_fields=["sprint"])
    return task


def scope_creep_tasks(sprint):
    """Tasks in this sprint with no commitment row — added after start."""
    return sprint.tasks.exclude(commitments__sprint=sprint)


def committed_hours(sprint):
    """Sum of estimate_hours_at_start across every SprintCommitment row."""
    total = Decimal(0)
    for commitment in sprint.commitments.all():
        if commitment.estimate_hours_at_start is not None:
            total += commitment.estimate_hours_at_start
    return total


def added_hours(sprint):
    """Sum of estimate_hours for scope-creep tasks (current estimate, since
    they were never frozen by a commitment)."""
    total = Decimal(0)
    for task in scope_creep_tasks(sprint):
        if task.estimate_hours is not None:
            total += task.estimate_hours
    return total


def write_daily_worklogs(sprint, *, as_of=None):
    """
    Write one WorkLog row per unfinished task in the sprint, snapshotting
    its current estimate as "remaining_hours" for today. Meant to run
    nightly via Celery beat. Reconstructing history from current state is
    impossible once estimates change — this daily row is the only honest
    source for the burndown.

    Unestimated tasks are treated as zero remaining, consistent with how
    they're treated everywhere else (docs/TECHNICAL_SPEC.md §4).
    """
    from tasks.models import Task
    from sprints.models import WorkLog

    as_of = as_of or timezone.now().date()
    written = []
    for task in sprint.tasks.exclude(state=Task.State.DONE):
        remaining = task.estimate_hours if task.estimate_hours is not None else Decimal(0)
        log, _created = WorkLog.objects.update_or_create(
            task=task, date=as_of, defaults={"remaining_hours": remaining}
        )
        written.append(log)
    return written


def velocity(project, *, sprint_count=3):
    """
    Average committed hours (never scope creep) across the most recently
    completed sprints, up to sprint_count. Counting scope creep here would
    let a chaotic sprint look fast and inflate the next sprint's plan.

    Returns None until at least sprint_count completed sprints exist —
    reporting a velocity from one lucky sprint would be worse than
    reporting nothing.
    """
    from sprints.models import Sprint

    completed = list(
        project.sprints.filter(state=Sprint.State.COMPLETED)
        .order_by("-started_at")[:sprint_count]
    )
    if len(completed) < sprint_count:
        return None

    total = sum(committed_hours(sprint) for sprint in completed)
    return total / Decimal(len(completed))
