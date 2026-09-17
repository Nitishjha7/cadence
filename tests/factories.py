import factory
from django.contrib.auth.models import User

from core import models


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@cadence.demo")


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Project

    name = factory.Sequence(lambda n: f"Project {n}")
    key = factory.Sequence(lambda n: f"P{n}")


class MemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Member

    user = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)
    role = models.Member.Role.CONTRIBUTOR
    weekly_hours = 40


class SprintFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Sprint

    project = factory.SubFactory(ProjectFactory)
    name = factory.Sequence(lambda n: f"Sprint {n}")
    starts_on = factory.Faker("date_object")
    ends_on = factory.Faker("date_object")
    state = models.Sprint.State.PLANNED


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Task

    project = factory.SubFactory(ProjectFactory)
    number = factory.Sequence(lambda n: n + 1)
    title = factory.Sequence(lambda n: f"Task {n}")
    state = models.Task.State.TODO


class TaskDependencyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.TaskDependency

    task = factory.SubFactory(TaskFactory)
    depends_on = factory.SubFactory(TaskFactory)


class SprintCommitmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.SprintCommitment

    sprint = factory.SubFactory(SprintFactory)
    task = factory.SubFactory(TaskFactory)
    estimate_hours_at_start = 8


class CapacityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Capacity

    member = factory.SubFactory(MemberFactory)
    sprint = factory.SubFactory(SprintFactory)
    available_hours = 40


class TimeOffFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.TimeOff

    member = factory.SubFactory(MemberFactory)
    starts_on = factory.Faker("date_object")
    ends_on = factory.Faker("date_object")


class WorkLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.WorkLog

    task = factory.SubFactory(TaskFactory)
    date = factory.Faker("date_object")
    remaining_hours = 8
