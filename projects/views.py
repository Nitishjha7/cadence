from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from projects.models import Member


class ProjectListView(LoginRequiredMixin, ListView):
    """The user's projects — the landing page after login."""

    template_name = "projects/project_list.html"
    context_object_name = "memberships"

    def get_queryset(self):
        return (
            Member.objects.filter(user=self.request.user)
            .select_related("project")
            .order_by("project__name")
        )
