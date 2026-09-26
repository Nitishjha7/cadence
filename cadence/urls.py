"""
URL configuration for cadence project.

The five screens (docs/UI_FLOW.md) live under projects/tasks/sprints, each
app owning its own urls.py.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("projects.urls")),
    path("", include("tasks.urls")),
    path("", include("sprints.urls")),
]
