from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView

from projects.views_base import ProjectPermissionMixin
from sprints.models import Sprint
from sprints.services import (
    SprintAlreadyStartedError,
    allocated_hours_for,
    is_over_allocated,
    unestimated_task_count_for,
)


class CapacityView(ProjectPermissionMixin, DetailView):
    """
    Screen 4 — docs/UI_FLOW.md §4. Load bars, leave, over-allocation.
    Uses the *frozen* Capacity row if the sprint has started (so numbers
    match what was committed to), falling back to the live calculation for
    a sprint still being planned.
    """

    model = Sprint
    pk_url_kwarg = "sprint_pk"
    context_object_name = "sprint"
    template_name = "sprints/capacity.html"

    def get_queryset(self):
        return Sprint.objects.filter(project=self.project)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprint = self.object
        rows = []
        for member in self.project.members.select_related("user"):
            capacity_row = sprint.capacities.filter(member=member).first()
            available = capacity_row.available_hours if capacity_row else None
            allocated = allocated_hours_for(member, sprint)
            time_off = member.time_off.filter(starts_on__lte=sprint.ends_on, ends_on__gte=sprint.starts_on)
            rows.append({
                "member": member,
                "available": available,
                "allocated": allocated,
                "over_allocated": is_over_allocated(member, sprint) if available is not None else False,
                "unestimated_count": unestimated_task_count_for(member, sprint),
                "time_off": time_off,
            })
        available_known = [r["available"] for r in rows if r["available"] is not None]

        context["rows"] = rows
        context["team_allocated"] = sum((r["allocated"] for r in rows), Decimal(0))
        context["team_available"] = sum(available_known, Decimal(0)) if available_known else None
        return context


class SprintDetailView(ProjectPermissionMixin, DetailView):
    """Screen 5 — docs/UI_FLOW.md §5. Sprint + burndown, scope creep visible."""

    model = Sprint
    pk_url_kwarg = "sprint_pk"
    context_object_name = "sprint"
    template_name = "sprints/sprint_detail.html"

    def get_queryset(self):
        return Sprint.objects.filter(project=self.project)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprint = self.object
        context["scope_creep_tasks"] = sprint.scope_creep_tasks() if sprint.started_at else []
        context["committed_hours"] = sprint.committed_hours if sprint.started_at else None
        context["added_hours"] = sprint.added_hours if sprint.started_at else None

        worklogs = {}
        if sprint.started_at:
            from sprints.models import WorkLog

            for log in WorkLog.objects.filter(task__sprint=sprint).order_by("date"):
                worklogs.setdefault(log.date, 0)
                worklogs[log.date] += log.remaining_hours
        context["burndown"] = sorted(worklogs.items())

        from sprints.services import velocity

        context["velocity"] = velocity(self.project)
        return context


class SprintStartView(ProjectPermissionMixin, View):
    """Manager-only transition planned -> active. docs/TECHNICAL_SPEC.md §5."""

    required_role = "manage"

    def post(self, request, *args, **kwargs):
        sprint = get_object_or_404(Sprint, pk=kwargs["sprint_pk"], project=self.project)
        try:
            sprint.start()
        except SprintAlreadyStartedError as exc:
            messages.error(request, str(exc))
        return redirect("sprints:sprint_detail", project_pk=self.project.pk, sprint_pk=sprint.pk)
