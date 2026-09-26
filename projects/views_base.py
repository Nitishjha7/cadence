"""
The permission mixin every view in this project uses. A new view that
forgets to inherit from ProjectPermissionMixin fails
tests/test_permissions.py::test_every_view_uses_the_permission_mixin
rather than silently shipping unprotected — see docs/architecture.md.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404

from projects.models import Member, Project
from projects.permissions import can_edit, can_manage, can_view


class ProjectPermissionMixin(LoginRequiredMixin):
    """
    Resolves `self.project` from the URL (a `project_pk` kwarg) and checks
    the requesting user is a member of it before the view runs.

    A user who isn't a member gets a 404, not a 403 — a 403 would confirm
    the project exists, which is itself information a member of a
    *different* project shouldn't get for free.

    `required_role` on the view class controls how much access is needed:
    "view" (default), "edit", or "manage".
    """

    required_role = "view"

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(Project, pk=kwargs.get("project_pk"))

        if not can_view(request.user, self.project):
            raise Http404("No project found matching the query")

        if self.required_role == "edit" and not can_edit(request.user, self.project):
            raise Http404("No project found matching the query")

        if self.required_role == "manage" and not can_manage(request.user, self.project):
            raise Http404("No project found matching the query")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["member"] = Member.objects.filter(user=self.request.user, project=self.project).first()
        return context
