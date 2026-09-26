"""
Permissions — docs/TEST_PLAN.md §5.

Object-level checks live in projects/permissions.py and are wired into
every view via ProjectPermissionMixin, not scattered `if` statements.
"""

import pytest
from django.test import Client
from django.urls import get_resolver, reverse

from projects.models import Member
from projects.permissions import can_edit, can_manage, can_view
from projects.views_base import ProjectPermissionMixin
from tests.factories import (
    MemberFactory,
    ProjectFactory,
    SprintFactory,
    TaskFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def test_viewer_cannot_create_a_task():
    project = ProjectFactory()
    viewer = MemberFactory(project=project, role=Member.Role.VIEWER)

    assert can_view(viewer.user, project) is True
    assert can_edit(viewer.user, project) is False


def test_contributor_cannot_start_a_sprint():
    project = ProjectFactory()
    contributor = MemberFactory(project=project, role=Member.Role.CONTRIBUTOR)

    assert can_edit(contributor.user, project) is True
    assert can_manage(contributor.user, project) is False


def test_manager_can_start_a_sprint():
    project = ProjectFactory()
    manager = MemberFactory(project=project, role=Member.Role.MANAGER)

    assert can_manage(manager.user, project) is True


def test_member_of_project_a_cannot_see_project_b_tasks():
    project_a = ProjectFactory()
    project_b = ProjectFactory()
    member_a = MemberFactory(project=project_a, role=Member.Role.VIEWER)

    assert can_view(member_a.user, project_a) is True
    assert can_view(member_a.user, project_b) is False


def test_a_user_with_no_membership_cannot_view_the_project():
    project = ProjectFactory()
    outsider = UserFactory()

    assert can_view(outsider, project) is False


# ---------------------------------------------------------------------------
# HTTP-level: 404, not 403 — a 403 would confirm the project exists
# ---------------------------------------------------------------------------


def test_member_of_project_a_gets_404_not_403_for_project_b_tasks():
    project_a = ProjectFactory()
    project_b = ProjectFactory()
    member_a = MemberFactory(project=project_a, role=Member.Role.VIEWER)
    task_b = TaskFactory(project=project_b, number=1)

    client = Client()
    client.force_login(member_a.user)
    url = reverse("tasks:task_detail", kwargs={"project_pk": project_b.pk, "task_pk": task_b.pk})

    response = client.get(url)

    assert response.status_code == 404


def test_an_outsider_gets_404_not_403_for_the_board():
    project = ProjectFactory()
    outsider = UserFactory()

    client = Client()
    client.force_login(outsider)
    url = reverse("tasks:board", kwargs={"project_pk": project.pk})

    response = client.get(url)

    assert response.status_code == 404


def test_viewer_gets_404_not_403_starting_a_sprint():
    project = ProjectFactory()
    viewer = MemberFactory(project=project, role=Member.Role.VIEWER)
    sprint = SprintFactory(project=project)

    client = Client()
    client.force_login(viewer.user)
    url = reverse("sprints:sprint_start", kwargs={"project_pk": project.pk, "sprint_pk": sprint.pk})

    response = client.post(url)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Every project-scoped view uses the mixin
# ---------------------------------------------------------------------------


# Views that legitimately don't take a project_pk (they list across
# projects, or don't exist yet) are the only allowed exemptions here — a
# new project-scoped view that forgets the mixin fails this test.
EXEMPT_VIEW_NAMES = {"ProjectListView"}


def _iter_view_classes(resolver=None):
    resolver = resolver or get_resolver()
    for pattern in resolver.url_patterns:
        if hasattr(pattern, "url_patterns"):
            yield from _iter_view_classes(pattern)
        else:
            view_class = getattr(pattern.callback, "view_class", None)
            if view_class is not None:
                yield view_class


def test_every_project_scoped_view_uses_the_permission_mixin():
    checked_any = False
    for view_class in _iter_view_classes():
        if view_class.__name__ in EXEMPT_VIEW_NAMES:
            continue
        if view_class.__module__.split(".")[0] not in ("tasks", "sprints", "projects"):
            continue  # admin, auth views, etc. are not project-scoped
        if view_class.__module__ == "projects.views_base":
            continue
        checked_any = True
        assert issubclass(view_class, ProjectPermissionMixin), (
            f"{view_class.__module__}.{view_class.__name__} does not inherit "
            "ProjectPermissionMixin — add it, or add the view to EXEMPT_VIEW_NAMES "
            "with a reason if it genuinely isn't project-scoped."
        )
    assert checked_any, "no view classes were found to check — has the URLconf changed shape?"
