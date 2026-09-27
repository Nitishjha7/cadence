"""
The scheduler-triggered worklog endpoint (sprints:write_worklogs).

Exists for deployments with no standing Celery beat process — a scheduler
(Cloud Scheduler in production) hits this over HTTP instead. Protected by
a shared secret header, not login, since the caller is a cron trigger.
"""

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from sprints.models import WorkLog
from tests.factories import SprintFactory, TaskFactory

pytestmark = pytest.mark.django_db

URL = "/internal/write-worklogs/"


def test_url_resolves_to_the_named_route():
    assert reverse("sprints:write_worklogs") == URL


@override_settings(CADENCE_CRON_SECRET="")
def test_rejects_every_caller_when_no_secret_is_configured():
    response = Client().post(URL, HTTP_X_CRON_SECRET="anything")
    assert response.status_code == 403


@override_settings(CADENCE_CRON_SECRET="the-real-secret")
def test_rejects_a_missing_secret_header():
    response = Client().post(URL)
    assert response.status_code == 403


@override_settings(CADENCE_CRON_SECRET="the-real-secret")
def test_rejects_the_wrong_secret():
    response = Client().post(URL, HTTP_X_CRON_SECRET="wrong")
    assert response.status_code == 403


@override_settings(CADENCE_CRON_SECRET="the-real-secret")
def test_accepts_the_right_secret_and_writes_worklogs():
    sprint = SprintFactory(state="active")
    TaskFactory(sprint=sprint, project=sprint.project, number=1, estimate_hours=5)

    response = Client().post(URL, HTTP_X_CRON_SECRET="the-real-secret")

    assert response.status_code == 200
    assert response.json() == {"worklogs_written": 1}
    assert WorkLog.objects.filter(task__sprint=sprint).exists()


@override_settings(CADENCE_CRON_SECRET="the-real-secret")
def test_get_is_not_allowed():
    response = Client().get(URL, HTTP_X_CRON_SECRET="the-real-secret")
    assert response.status_code == 405
