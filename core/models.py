import uuid

from django.conf import settings
from django.db import models


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    key = models.CharField(max_length=10, unique=True, help_text="Task prefix, e.g. CAD")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Member(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        CONTRIBUTOR = "contributor", "Contributor"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CONTRIBUTOR)
    weekly_hours = models.PositiveIntegerField(default=40)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "project"], name="unique_member_per_project"),
        ]

    def __str__(self):
        return f"{self.user} ({self.project})"


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


class Task(models.Model):
    class State(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    # "blocked" is deliberately not a State value — it is derived, see is_blocked().

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    number = models.PositiveIntegerField(help_text="Sequential per project, e.g. 14 in CAD-14")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.TODO)
    assignee = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks"
    )
    estimate_hours = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Null means unestimated, which capacity must handle",
    )
    sprint = models.ForeignKey(
        Sprint, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "number"], name="unique_task_number_per_project"),
        ]
        ordering = ["project", "number"]

    def __str__(self):
        return f"{self.key}: {self.title}"

    @property
    def key(self):
        return f"{self.project.key}-{self.number}"

    @property
    def is_blocked(self):
        """A task is blocked if any dependency is not done. Derived, never stored."""
        return self.dependencies.exclude(depends_on__state=Task.State.DONE).exists()


class TaskDependency(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependencies")
    depends_on = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependents")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "depends_on"], name="unique_task_dependency_edge"),
            models.CheckConstraint(
                check=~models.Q(task=models.F("depends_on")),
                name="task_cannot_depend_on_itself",
            ),
        ]

    def __str__(self):
        return f"{self.task.key} depends on {self.depends_on.key}"

    def clean(self):
        from django.core.exceptions import ValidationError

        from core.graph import would_create_cycle

        if self.task_id == self.depends_on_id:
            raise ValidationError("A task cannot depend on itself.")

        cycle_path = would_create_cycle(self.task, self.depends_on)
        if cycle_path is not None:
            path_str = " -> ".join(f"{t.key} ({t.title})" for t in cycle_path)
            raise ValidationError(
                f"Circular dependency:\n  {path_str}\nNeither task could ever start."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


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
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="commitments")
    estimate_hours_at_start = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sprint", "task"], name="unique_commitment_per_sprint_task"),
        ]

    def __str__(self):
        return f"{self.task.key} committed to {self.sprint}"


class Capacity(models.Model):
    """Computed at sprint start, stored. See docs/TECHNICAL_SPEC.md §4."""

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
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="work_logs")
    date = models.DateField()
    remaining_hours = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "date"], name="unique_worklog_per_task_day"),
        ]
        ordering = ["date"]

    def __str__(self):
        return f"{self.task.key} on {self.date}: {self.remaining_hours}h left"
