from django.urls import path

from tasks import views

app_name = "tasks"

urlpatterns = [
    path("projects/<uuid:project_pk>/board/", views.BoardView.as_view(), name="board"),
    path("projects/<uuid:project_pk>/tasks/<uuid:task_pk>/", views.TaskDetailView.as_view(), name="task_detail"),
    path(
        "projects/<uuid:project_pk>/tasks/<uuid:task_pk>/state/",
        views.TaskStateChangeView.as_view(),
        name="task_state_change",
    ),
    path(
        "projects/<uuid:project_pk>/tasks/<uuid:task_pk>/dependencies/",
        views.AddDependencyView.as_view(),
        name="add_dependency",
    ),
]
