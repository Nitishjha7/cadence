from django.urls import path

from sprints import views

app_name = "sprints"

urlpatterns = [
    path("projects/<uuid:project_pk>/sprints/<uuid:sprint_pk>/", views.SprintDetailView.as_view(), name="sprint_detail"),
    path("projects/<uuid:project_pk>/sprints/<uuid:sprint_pk>/capacity/", views.CapacityView.as_view(), name="capacity"),
    path("projects/<uuid:project_pk>/sprints/<uuid:sprint_pk>/start/", views.SprintStartView.as_view(), name="sprint_start"),
    # Hit by a scheduler (Cloud Scheduler in production), not a browser —
    # see WriteWorklogsView. Deliberately outside the /projects/<pk>/ tree.
    path("internal/write-worklogs/", views.WriteWorklogsView.as_view(), name="write_worklogs"),
]
