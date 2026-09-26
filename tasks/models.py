import uuid

from django.core.exceptions import ValidationError
from django.db import models

from projects.models import Member, Project


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
        "sprints.Sprint", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
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
        """
        A task is blocked if any dependency is not done. Derived, never
        stored — see docs/architecture.md.

        If `dependencies__depends_on` was prefetched, reuse that cache
        instead of issuing `.exclude().exists()`, which would otherwise
        hit the database once per task and quietly reintroduce the N+1 a
        prefetch is supposed to prevent — see tests/test_queries.py.
        """
        if "dependencies" in getattr(self, "_prefetched_objects_cache", {}):
            return any(dep.depends_on.state != Task.State.DONE for dep in self.dependencies.all())
        return self.dependencies.exclude(depends_on__state=Task.State.DONE).exists()


class TaskDependency(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependencies")
    depends_on = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependents")

    class Meta:
        verbose_name_plural = "task dependencies"
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
        from tasks.services import would_create_cycle

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
