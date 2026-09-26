from django.urls import path

from sprints import views

app_name = "sprints"

urlpatterns = [
    path("projects/<uuid:project_pk>/sprints/<uuid:sprint_pk>/", views.SprintDetailView.as_view(), name="sprint_detail"),
    path("projects/<uuid:project_pk>/sprints/<uuid:sprint_pk>/capacity/", views.CapacityView.as_view(), name="capacity"),
    path("projects/<uuid:project_pk>/sprints/<uuid:sprint_pk>/start/", views.SprintStartView.as_view(), name="sprint_start"),
]
