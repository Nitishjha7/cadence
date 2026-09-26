"""Celery tasks for sprints — the nightly burndown snapshot."""

from celery import shared_task


@shared_task
def write_daily_worklogs_for_active_sprints():
    """
    Run nightly via Celery beat. Writes today's WorkLog row for every
    unfinished task in every currently-active sprint across all projects.
    See sprints.services.write_daily_worklogs for the per-sprint logic and
    docs/architecture.md for why this can't be reconstructed later.
    """
    from sprints.models import Sprint
    from sprints.services import write_daily_worklogs

    written = 0
    for sprint in Sprint.objects.filter(state=Sprint.State.ACTIVE):
        written += len(write_daily_worklogs(sprint))
    return written
