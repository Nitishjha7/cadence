import factory
from django.contrib.auth.models import User

from projects import models as projects_models
from sprints import models as sprints_models
from tasks import models as tasks_models


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@cadence.demo")


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = projects_models.Project

    name = factory.Sequence(lambda n: f"Project {n}")
    key = factory.Sequence(lambda n: f"P{n}")


class MemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = projects_models.Member

    user = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)
    role = projects_models.Member.Role.CONTRIBUTOR
    weekly_hours = 40


class SprintFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = sprints_models.Sprint

    project = factory.SubFactory(ProjectFactory)
    name = factory.Sequence(lambda n: f"Sprint {n}")
    starts_on = factory.Faker("date_object")
    ends_on = factory.Faker("date_object")
    state = sprints_models.Sprint.State.PLANNED


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = tasks_models.Task

    project = factory.SubFactory(ProjectFactory)
    number = factory.Sequence(lambda n: n + 1)
    title = factory.Sequence(lambda n: f"Task {n}")
    state = tasks_models.Task.State.TODO


class TaskDependencyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = tasks_models.TaskDependency

    task = factory.SubFactory(TaskFactory)
    depends_on = factory.SubFactory(TaskFactory)


class SprintCommitmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = sprints_models.SprintCommitment

    sprint = factory.SubFactory(SprintFactory)
    task = factory.SubFactory(TaskFactory)
    estimate_hours_at_start = 8


class CapacityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = sprints_models.Capacity

    member = factory.SubFactory(MemberFactory)
    sprint = factory.SubFactory(SprintFactory)
    available_hours = 40


class TimeOffFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = sprints_models.TimeOff

    member = factory.SubFactory(MemberFactory)
    starts_on = factory.Faker("date_object")
    ends_on = factory.Faker("date_object")


class WorkLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = sprints_models.WorkLog

    task = factory.SubFactory(TaskFactory)
    date = factory.Faker("date_object")
    remaining_hours = 8
