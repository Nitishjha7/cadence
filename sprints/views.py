from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView

from projects.views_base import ProjectPermissionMixin
from sprints.models import Sprint, TimeOff, WorkLog
from sprints.services import SprintAlreadyStartedError, velocity


class CapacityView(ProjectPermissionMixin, DetailView):
    """
    Screen 4 — docs/UI_FLOW.md §4. Load bars, leave, over-allocation.
    Uses the *frozen* Capacity row if the sprint has started (so numbers
    match what was committed to), falling back to a live calculation for a
    sprint still being planned.

    Deliberately does not call sprints.services' per-member functions in a
    loop here — each of those runs its own query, which would reintroduce
    the N+1 this view exists to avoid (docs/TECHNICAL_SPEC.md §3's
    "prefetch or it's an N+1" lesson applies just as much to capacity as to
    is_blocked). Instead everything is fetched in a handful of queries up
    front and matched up in Python — see tests/test_queries.py.
    """

    model = Sprint
    pk_url_kwarg = "sprint_pk"
    context_object_name = "sprint"
    template_name = "sprints/capacity.html"

    def get_queryset(self):
        return Sprint.objects.filter(project=self.project)

    def get_context_data(self, **kwargs):
        from tasks.models import Task

        context = super().get_context_data(**kwargs)
        sprint = self.object
        members = list(self.project.members.select_related("user"))

        capacity_by_member = {
            c.member_id: c.available_hours for c in sprint.capacities.all()
        }

        time_off_by_member = defaultdict(list)
        for time_off in TimeOff.objects.filter(
            member__project=self.project, starts_on__lte=sprint.ends_on, ends_on__gte=sprint.starts_on
        ).select_related("member"):
            time_off_by_member[time_off.member_id].append(time_off)

        allocated_by_member = defaultdict(Decimal)
        unestimated_by_member = defaultdict(int)
        assigned_tasks = (
            Task.objects.filter(project=self.project, sprint=sprint, assignee__isnull=False)
            .exclude(state=Task.State.DONE)
        )
        for task in assigned_tasks:
            if task.estimate_hours is not None:
                allocated_by_member[task.assignee_id] += task.estimate_hours
            else:
                unestimated_by_member[task.assignee_id] += 1

        rows = []
        for member in members:
            available = capacity_by_member.get(member.id)
            allocated = allocated_by_member[member.id]
            rows.append({
                "member": member,
                "available": available,
                "allocated": allocated,
                "over_allocated": available is not None and allocated > available,
                "unestimated_count": unestimated_by_member[member.id],
                "time_off": time_off_by_member[member.id],
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
            for log in WorkLog.objects.filter(task__sprint=sprint).order_by("date"):
                worklogs.setdefault(log.date, 0)
                worklogs[log.date] += log.remaining_hours
        context["burndown"] = sorted(worklogs.items())

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
