"""
seed_demo — docs/UI_FLOW.md's seed data specification.

This is not a fixture, it is the demo (per that doc). Every requirement in
its table is built here on purpose, not incidentally:

  1 project, ~45 tasks             -- the board looks worked-in
  3 sprints: 2 completed, 1 active -- velocity needs history
  6 members, mixed roles           -- permissions have something to enforce
  a dependency chain 4+ deep       -- "blocked by" is not all one level
  a diamond in the graph           -- proves the legal case exists in real data
  a pair that triggers a cycle     -- reproducible in two clicks (see below)
  one member on leave mid-sprint   -- the capacity screen
  two members over-allocated       -- the warning has to be visible
  2-3 unestimated tasks            -- the "counted as zero" case
  scope creep in the active sprint -- 2 tasks added day 8, worklogs before/after
  daily worklogs across the sprint -- burndown needs real daily rows

Task numbers below deliberately match the worked examples in
docs/UI_FLOW.md and docs/DEMO_SCRIPT.md (CAD-3 API keys, CAD-7 Payment
gateway, CAD-14 Webhook retry, CAD-18 Settlement, CAD-31/32 scope creep) so
the running app reads the same as the docs. After any change here, re-run
and confirm clicking "Add dependency" on CAD-3 -> CAD-7 still rejects.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from projects.models import Member, Project
from sprints.models import Sprint, TimeOff
from sprints.services import write_daily_worklogs
from tasks.models import Task, TaskDependency

TODAY = date(2026, 9, 15)  # the "today" this demo is staged around


class Command(BaseCommand):
    help = "Seed a realistic demo project. Use --reset to wipe existing demo data first."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the demo project first.")

    def handle(self, *args, **options):
        if options["reset"]:
            Project.objects.filter(key="CAD").delete()
            User.objects.filter(username__endswith="@cadence.demo").delete()
            self.stdout.write("Wiped existing demo data.")

        with transaction.atomic():
            project = self._create_members(Project.objects.create(name="Payments Revamp", key="CAD"))
            self._tasks_by_number = {}
            active_sprint = self._build_active_sprint_tasks(project)
            self._create_completed_sprints(project)
            self._start_and_populate_active_sprint(project, active_sprint)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {project.name} ({project.key}): "
            f"{project.tasks.count()} tasks, {project.members.count()} members, "
            f"{project.sprints.count()} sprints."
        ))
        self.stdout.write("Cycle demo: open CAD-3, add dependency on CAD-7 — must reject.")

    # -- Members ----------------------------------------------------------

    def _create_members(self, project):
        roster = [
            ("manager@cadence.demo", "Rahul Sharma", Member.Role.MANAGER, 40),
            ("dev@cadence.demo", "Priya Mehta", Member.Role.CONTRIBUTOR, 40),
            ("viewer@cadence.demo", "Sneha Patel", Member.Role.VIEWER, 40),
            ("amit@cadence.demo", "Amit Kumar", Member.Role.CONTRIBUTOR, 40),
            ("vikram@cadence.demo", "Vikram Singh", Member.Role.CONTRIBUTOR, 40),
            ("neha@cadence.demo", "Neha Gupta", Member.Role.CONTRIBUTOR, 20),  # part-time
        ]
        members = {}
        for email, name, role, weekly_hours in roster:
            first, _, last = name.partition(" ")
            user, _ = User.objects.update_or_create(
                username=email, defaults={"email": email, "first_name": first, "last_name": last}
            )
            user.set_password("password")
            user.save()
            members[email] = Member.objects.create(
                user=user, project=project, role=role, weekly_hours=weekly_hours
            )
        self._members = members
        return project

    # -- Active sprint's tasks, numbered to match the docs -----------------

    def _task(self, project, number, title, estimate=None, state=Task.State.TODO, sprint=None, assignee=None):
        task = Task.objects.create(
            project=project, number=number, title=title,
            estimate_hours=estimate, state=state, sprint=sprint, assignee=assignee,
        )
        self._tasks_by_number[number] = task
        return task

    def _build_active_sprint_tasks(self, project):
        sprint = Sprint.objects.create(
            project=project, name="Sprint 3",
            starts_on=TODAY - timedelta(days=7), ends_on=TODAY + timedelta(days=6),
        )
        m = self._members
        manager, priya, amit, vikram, neha = (
            m["manager@cadence.demo"], m["dev@cadence.demo"], m["amit@cadence.demo"],
            m["vikram@cadence.demo"], m["neha@cadence.demo"],
        )
        T = lambda n, *a, **kw: self._task(project, n, *a, **kw)  # noqa: E731

        T(1, "Project scaffolding", estimate=Decimal(3), state=Task.State.DONE, assignee=manager)
        T(2, "Sprint planning", estimate=Decimal(2), state=Task.State.DONE, assignee=manager)
        # CAD-3/CAD-7: the fixed cycle-demo pair (docs/DEMO_SCRIPT.md).
        T(3, "API keys", estimate=Decimal(3), state=Task.State.DONE, assignee=manager)
        T(4, "Design review", estimate=Decimal(2), state=Task.State.DONE, assignee=priya)
        T(5, "DB schema", estimate=Decimal(5), state=Task.State.DONE, assignee=amit)
        T(6, "CI pipeline", estimate=Decimal(3), state=Task.State.DONE, assignee=vikram)
        payment_gateway = T(7, "Payment gateway integration", estimate=Decimal(13), sprint=sprint, assignee=amit)
        TaskDependency.objects.create(task=payment_gateway, depends_on=self._tasks_by_number[3])

        # Priya: 3 card-form tasks (over capacity), on leave mid-sprint.
        T(8, "Card form design", estimate=Decimal(3), state=Task.State.DONE, assignee=priya)
        T(9, "Card form", estimate=Decimal(26), sprint=sprint, assignee=priya)
        T(10, "Card form validation", estimate=Decimal(13), sprint=sprint, assignee=priya)
        T(11, "Card form error states", estimate=Decimal(13), sprint=sprint, assignee=priya)
        TimeOff.objects.create(
            member=priya, starts_on=TODAY - timedelta(days=3), ends_on=TODAY, reason="Festival leave"
        )

        T(12, "Refund flow", estimate=Decimal(8), sprint=sprint, assignee=amit)

        # A 4+ deep linear chain hanging off the cycle-pair's payment_gateway
        # (CAD-7), so "blocked by" is not all one level:
        #   payment_gateway(7) -> webhook_retry(14) -> settlement(18)
        #   -> ledger_export(15) -> audit_report(16)
        T(13, "Webhook signature validation", estimate=Decimal(5), state=Task.State.DONE, assignee=amit)
        webhook_retry = T(14, "Webhook retry logic", estimate=Decimal(8), sprint=sprint, assignee=None)
        TaskDependency.objects.create(task=webhook_retry, depends_on=payment_gateway)
        settlement = T(18, "Settlement reconciliation", sprint=sprint, assignee=None)  # unestimated
        TaskDependency.objects.create(task=settlement, depends_on=webhook_retry)
        TaskDependency.objects.create(task=settlement, depends_on=self._tasks_by_number[12])
        ledger_export = T(15, "Ledger export", estimate=Decimal(6), sprint=sprint, assignee=vikram)
        TaskDependency.objects.create(task=ledger_export, depends_on=settlement)
        audit_report = T(16, "Audit report", estimate=Decimal(4), sprint=sprint, assignee=vikram)
        TaskDependency.objects.create(task=audit_report, depends_on=ledger_export)

        T(17, "Extra reporting work", estimate=Decimal(75), sprint=sprint, assignee=vikram)  # over capacity

        # A diamond: fraud_check blocks both hardening and rate-limiting,
        # which both block go-live.
        fraud_check = T(19, "Fraud check hook", estimate=Decimal(5), sprint=sprint, assignee=priya)
        webhook_hardening = T(20, "Webhook hardening", estimate=Decimal(3), sprint=sprint, assignee=priya)
        rate_limiting = T(21, "Rate limiting", estimate=Decimal(3), sprint=sprint, assignee=None)
        go_live = T(22, "Go-live checklist", estimate=Decimal(2), sprint=sprint, assignee=manager)
        TaskDependency.objects.create(task=webhook_hardening, depends_on=fraud_check)
        TaskDependency.objects.create(task=rate_limiting, depends_on=fraud_check)
        TaskDependency.objects.create(task=go_live, depends_on=webhook_hardening)
        TaskDependency.objects.create(task=go_live, depends_on=rate_limiting)

        # Unestimated tasks (18 above, plus these two).
        T(23, "Investigate flaky webhook test", estimate=None, sprint=sprint, assignee=amit)
        T(24, "Spike: batching payouts", estimate=None, sprint=sprint, assignee=amit)

        T(25, "Update onboarding docs", estimate=Decimal(4), sprint=sprint, assignee=neha)
        T(26, "Update API docs", estimate=Decimal(3), sprint=sprint, assignee=neha)

        # Fill out the active sprint's own numbering so the board looks
        # worked-in; the completed sprints and scope creep take the numbers
        # after this. Only unassigned or manager/amit/neha here — Priya and
        # Vikram's over-allocation above must not be diluted by filler.
        filler_states = [Task.State.TODO, Task.State.IN_PROGRESS, Task.State.DONE]
        filler_assignees = [manager, amit, neha, None]
        for i, n in enumerate(range(27, 40)):
            T(
                n, f"Miscellaneous task {n}",
                estimate=Decimal([2, 3, 5, 8][i % 4]),
                state=filler_states[i % len(filler_states)],
                sprint=sprint if i % 2 == 0 else None,
                assignee=filler_assignees[i % len(filler_assignees)],
            )

        return sprint

    def _create_completed_sprints(self, project):
        sprints = []
        for i in range(2):
            starts = TODAY - timedelta(days=42 - (i * 14))
            ends = starts + timedelta(days=13)
            sprint = Sprint.objects.create(
                project=project, name=f"Sprint {i + 1}", starts_on=starts, ends_on=ends
            )
            next_number = project.tasks.count() + 1
            tasks = [
                self._task(
                    project, next_number + j, f"Sprint {i + 1} task {j + 1}",
                    estimate=Decimal(8), state=Task.State.DONE, sprint=sprint,
                )
                for j in range(4)
            ]
            sprint.start(now=self._as_datetime(starts))
            for task in tasks:
                task.state = Task.State.DONE
                task.save(update_fields=["state"])
            sprint.state = Sprint.State.COMPLETED
            sprint.save(update_fields=["state"])
            sprints.append(sprint)
        return sprints

    def _start_and_populate_active_sprint(self, project, sprint):
        sprint.start(now=self._as_datetime(sprint.starts_on))

        for offset in range(8):  # days 0-7: before scope creep
            write_daily_worklogs(sprint, as_of=sprint.starts_on + timedelta(days=offset))

        # Scope creep: two tasks added on day 8, numbered 31/32 to match
        # docs/UI_FLOW.md's burndown mockup exactly.
        day_8 = sprint.starts_on + timedelta(days=7)
        next_number = project.tasks.count() + 1
        creep_1 = self._task(
            project, next_number, "Fraud check hook follow-up",
            estimate=Decimal(8), assignee=self._members["dev@cadence.demo"],
        )
        creep_2 = self._task(
            project, next_number + 1, "Retry backoff tuning",
            estimate=Decimal(8), assignee=self._members["amit@cadence.demo"],
        )
        for task in (creep_1, creep_2):
            sprint.add_task(task)
        write_daily_worklogs(sprint, as_of=day_8)

        for offset in range(8, (TODAY - sprint.starts_on).days + 1):
            write_daily_worklogs(sprint, as_of=sprint.starts_on + timedelta(days=offset))

    @staticmethod
    def _as_datetime(d):
        return timezone.make_aware(timezone.datetime(d.year, d.month, d.day, 9, 0))
