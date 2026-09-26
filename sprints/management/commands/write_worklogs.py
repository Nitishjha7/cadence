from django.core.management.base import BaseCommand

from sprints.tasks import write_daily_worklogs_for_active_sprints


class Command(BaseCommand):
    help = (
        "Write today's WorkLog row for every unfinished task in every active "
        "sprint. Normally runs nightly via Celery beat; this lets it be run "
        "by hand for demos (see docs/setup.md)."
    )

    def handle(self, *args, **options):
        count = write_daily_worklogs_for_active_sprints()
        self.stdout.write(self.style.SUCCESS(f"Wrote {count} worklog row(s)."))
