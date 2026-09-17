import pytest

from tests.factories import ProjectFactory, TaskFactory

pytestmark = pytest.mark.django_db


def test_project_and_task_can_be_created():
    project = ProjectFactory(name="Cadence", key="CAD")
    task = TaskFactory(project=project, number=1, title="Set up repo")

    assert task.key == "CAD-1"
    assert task.is_blocked is False
