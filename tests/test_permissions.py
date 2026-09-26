"""
Permissions — docs/TEST_PLAN.md §5.

Object-level checks live in projects/permissions.py and are wired into
every view via ProjectPermissionMixin, not scattered `if` statements.
"""

import pytest

from projects.models import Member
from projects.permissions import can_edit, can_manage, can_view
from tests.factories import MemberFactory, ProjectFactory, UserFactory

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
