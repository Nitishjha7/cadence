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
