# Setup

> Nothing is built yet. This is the intended setup, written ahead of the code so
> Phase 1 has a target. It will be verified and corrected once the code exists.

---

## Requirements

- Docker + Docker Compose
- Python 3.12 (only if running outside Docker)

---

## Quick start

```bash
git clone <repo>
cd cadence

cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser
```

| | |
|---|---|
| App | http://localhost:8005 |
| Admin | http://localhost:8005/admin/ |
| Postgres | localhost:5437 |

Demo logins:

| Role | Login | Sees |
|---|---|---|
| Manager | `manager@cadence.demo` / `password` | Everything, can start sprints |
| Contributor | `dev@cadence.demo` / `password` | Can edit tasks, cannot start sprints |
| Viewer | `viewer@cadence.demo` / `password` | Read only |

All three are worth showing — the permission model is part of the project.

Ports are offset from the other projects in the portfolio so several can run at
once.

---

## Services

| Service | Purpose |
|---|---|
| `web` | Django + gunicorn |
| `postgres` | PostgreSQL 16 |
| `redis` | Celery broker |
| `worker` | Celery worker |
| `beat` | Celery beat — nightly worklog snapshot, overdue checks |

---

## Commands

```bash
# Demo data
python manage.py seed_demo
python manage.py seed_demo --reset      # wipe first

# Burndown data (normally nightly via beat)
python manage.py write_worklogs

# Tests
pytest
pytest tests/test_dependency_graph.py
pytest -n auto
```

---

## Environment

```env
DEBUG=1
SECRET_KEY=...

DATABASE_URL=postgres://cadence:cadence@postgres:5432/cadence
CELERY_BROKER_URL=redis://redis:6379/0
```

No secret has a fallback default. A missing `SECRET_KEY` should fail loudly at
startup rather than silently running with something insecure.

---

## Notes

- The `beat` container must be running for burndown data to accumulate on its own.
  `write_worklogs` can be run by hand for demos.
- `seed_demo` writes daily worklogs across the active sprint, so the burndown has
  real daily rows rather than two endpoints.
- **After any seeder change, verify the cycle demo still reproduces** — the two
  tasks used in [DEMO_SCRIPT.md](DEMO_SCRIPT.md) §2 must still trigger the
  rejection.
