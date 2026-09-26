"""
Query counts — docs/TEST_PLAN.md §6.

Derived is_blocked makes N+1 the natural failure mode
(docs/TECHNICAL_SPEC.md §3). These tests are what stop it returning
silently: they assert the board and capacity views run in a constant
number of queries, independent of how many tasks or members exist.
"""

import pytest
from django.test import Client
from django.urls import reverse

from tests.factories import MemberFactory, ProjectFactory, SprintFactory, TaskDependencyFactory, TaskFactory

pytestmark = pytest.mark.django_db


def logged_in_client(member):
    client = Client()
    client.force_login(member.user)
    return client


def test_board_renders_in_constant_queries(django_assert_num_queries):
    project = ProjectFactory()
    manager = MemberFactory(project=project, role="manager")
    tasks = [TaskFactory(project=project, number=i + 1, assignee=manager) for i in range(45)]
    for i in range(1, 45):
        TaskDependencyFactory(task=tasks[i], depends_on=tasks[i - 1])

    client = logged_in_client(manager)
    url = reverse("tasks:board", kwargs={"project_pk": project.pk})

    # Warm up the client/session query before measuring, so only the
    # view's own queries are counted.
    client.get(url)

    with django_assert_num_queries(12):
        response = client.get(url)
    assert response.status_code == 200


def test_board_query_count_does_not_scale_with_task_count(django_assert_num_queries):
    project = ProjectFactory()
    manager = MemberFactory(project=project, role="manager")
    url_kwargs = {"project_pk": project.pk}
    client = logged_in_client(manager)
    client.get(reverse("tasks:board", kwargs=url_kwargs))

    small = [TaskFactory(project=project, number=i + 1, assignee=manager) for i in range(10)]
    for i in range(1, 10):
        TaskDependencyFactory(task=small[i], depends_on=small[i - 1])

    with django_assert_num_queries(12):
        client.get(reverse("tasks:board", kwargs=url_kwargs))

    big = [TaskFactory(project=project, number=100 + i, assignee=manager) for i in range(80)]
    for i in range(1, 80):
        TaskDependencyFactory(task=big[i], depends_on=big[i - 1])

    with django_assert_num_queries(12):
        client.get(reverse("tasks:board", kwargs=url_kwargs))


def test_capacity_view_does_not_scale_queries_with_members(django_assert_num_queries):
    project = ProjectFactory()
    manager = MemberFactory(project=project, role="manager")
    sprint = SprintFactory(project=project)
    client = logged_in_client(manager)
    url = reverse("sprints:capacity", kwargs={"project_pk": project.pk, "sprint_pk": sprint.pk})
    client.get(url)

    with django_assert_num_queries(10):
        client.get(url)

    for _ in range(10):
        MemberFactory(project=project)

    # Same query count with 11 members as with 1 — capacity/time-off/task
    # data is fetched in a handful of queries up front and matched to
    # members in Python, not looped per member.
    with django_assert_num_queries(10):
        client.get(url)
