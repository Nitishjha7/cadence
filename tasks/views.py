from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, TemplateView

from projects.views_base import ProjectPermissionMixin
from tasks.models import Task, TaskDependency


class BoardView(ProjectPermissionMixin, TemplateView):
    """
    Screen 1 — docs/UI_FLOW.md §1. Tasks grouped by state, blocked tasks
    greyed with what blocks them named.

    prefetch_related('dependencies__depends_on') is what keeps is_blocked
    from issuing a query per task — see docs/TECHNICAL_SPEC.md §3 and
    tests/test_queries.py, which pins the query count directly.
    """

    template_name = "tasks/board.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tasks = (
            self.project.tasks
            .select_related("assignee__user")
            .prefetch_related("dependencies__depends_on")
        )
        context["columns"] = [
            (Task.State.TODO, tasks.filter(state=Task.State.TODO)),
            (Task.State.IN_PROGRESS, tasks.filter(state=Task.State.IN_PROGRESS)),
            (Task.State.DONE, tasks.filter(state=Task.State.DONE)),
        ]
        context["active_sprint"] = self.project.sprints.filter(state="active").first()
        return context


class TaskDetailView(ProjectPermissionMixin, DetailView):
    """Screen 2 — docs/UI_FLOW.md §2. Dependencies in both directions."""

    model = Task
    template_name = "tasks/task_detail.html"
    pk_url_kwarg = "task_pk"
    context_object_name = "task"

    def get_queryset(self):
        return Task.objects.filter(project=self.project).prefetch_related(
            "dependencies__depends_on", "dependents__task"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["other_tasks"] = (
            Task.objects.filter(project=self.project)
            .exclude(pk=self.object.pk)
            .order_by("number")
        )
        return context


class TaskStateChangeView(ProjectPermissionMixin, View):
    """
    Changes a task's state. A blocked task cannot move to in_progress or
    done — the state selector is disabled in the template for the same
    reason, but the server is the actual enforcement point (a disabled
    <select> is a UI hint, not a guarantee).
    """

    required_role = "edit"

    def post(self, request, *args, **kwargs):
        task = get_object_or_404(Task, pk=kwargs["task_pk"], project=self.project)
        new_state = request.POST.get("state")

        if new_state in (Task.State.IN_PROGRESS, Task.State.DONE) and task.is_blocked:
            return redirect("tasks:task_detail", project_pk=self.project.pk, task_pk=task.pk)

        if new_state in Task.State.values:
            task.state = new_state
            task.save(update_fields=["state"])

        return redirect("tasks:task_detail", project_pk=self.project.pk, task_pk=task.pk)


class AddDependencyView(ProjectPermissionMixin, DetailView):
    """
    Screen 3 — docs/UI_FLOW.md §3, the most important interaction in the
    application. An inline HTMX form on the task detail page; on success it
    swaps in the updated dependency list, on cycle rejection it swaps in
    the error box naming the actual path.
    """

    required_role = "edit"
    model = Task
    pk_url_kwarg = "task_pk"
    context_object_name = "task"
    template_name = "tasks/_dependencies.html"

    def get_queryset(self):
        return Task.objects.filter(project=self.project)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        depends_on_id = request.POST.get("depends_on")
        depends_on = get_object_or_404(Task, pk=depends_on_id, project=self.project)

        error = None
        try:
            TaskDependency.objects.create(task=self.object, depends_on=depends_on)
        except ValidationError as exc:
            error = "\n".join(exc.messages) if hasattr(exc, "messages") else str(exc)

        context = self.get_context_data(object=self.object)
        context["error"] = error
        return render(request, self.template_name, context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["other_tasks"] = (
            Task.objects.filter(project=self.project)
            .exclude(pk=self.object.pk)
            .order_by("number")
        )
        return context
