import uuid

from django.db import models

from projects.models import Member, Project


class Sprint(models.Model):
    class State(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sprints")
    name = models.CharField(max_length=100)
    starts_on = models.DateField()
    ends_on = models.DateField()
    state = models.CharField(max_length=20, choices=State.choices, default=State.PLANNED)
    started_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.project.key})"

    # Thin wrappers over sprints.services — the logic lives there so it can
    # be reasoned about and imported without the ORM model in the way; these
    # exist only for the ergonomic `sprint.start()` call site.

    def start(self, *, now=None):
        from sprints.services import start_sprint

        return start_sprint(self, now=now)

    def add_task(self, task):
        from sprints.services import add_task_to_sprint

        return add_task_to_sprint(self, task)

    def scope_creep_tasks(self):
        from sprints.services import scope_creep_tasks

        return scope_creep_tasks(self)

    @property
    def committed_hours(self):
        from sprints.services import committed_hours

        return committed_hours(self)

    @property
    def added_hours(self):
        from sprints.services import added_hours

        return added_hours(self)


class SprintCommitment(models.Model):
    """
    Written once, when a sprint starts. This is the scope snapshot: a task in
    an active sprint with no commitment row here was added after the start
    (scope creep), and estimate_hours_at_start is copied rather than
    referenced so a later re-estimate does not retroactively change what was
    committed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey(Sprint, on_delete=models.CASCADE, related_name="commitments")
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="commitments")
    estimate_hours_at_start = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sprint", "task"], name="unique_commitment_per_sprint_task"),
        ]

    def __str__(self):
        return f"{self.task.key} committed to {self.sprint}"


class Capacity(models.Model):
    """Computed at sprint start, stored. See docs/architecture.md."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="capacities")
    sprint = models.ForeignKey(Sprint, on_delete=models.CASCADE, related_name="capacities")
    available_hours = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["member", "sprint"], name="unique_capacity_per_member_sprint"),
        ]

    def __str__(self):
        return f"{self.member} - {self.sprint}: {self.available_hours}h"


class TimeOff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="time_off")
    starts_on = models.DateField()
    ends_on = models.DateField()
    reason = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.member} off {self.starts_on}..{self.ends_on}"


class WorkLog(models.Model):
    """
    One row per task per day, written by a nightly Celery task. This is what
    the burndown is drawn from — reconstructing history from current state is
    not possible once estimates change.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="work_logs")
    date = models.DateField()
    remaining_hours = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "date"], name="unique_worklog_per_task_day"),
        ]
        ordering = ["date"]

    def __str__(self):
        return f"{self.task.key} on {self.date}: {self.remaining_hours}h left"
