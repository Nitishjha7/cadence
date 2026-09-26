# Setup

Docker Desktop is the only requirement.

## Running it

```bash
git clone <repo>
cd cadence

cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
```

| Service | URL |
|---|---|
| App | http://localhost:8005 |
| Admin | http://localhost:8005/admin/ |
| Postgres | localhost:5437 |

Ports are offset from other local projects so several can run at once.

## Demo logins

| Role | Login | Sees |
|---|---|---|
| Manager | `manager@cadence.demo` / `password` | Everything, can start sprints, reaches `/admin/` |
| Contributor | `dev@cadence.demo` / `password` | Can edit tasks, cannot start sprints |
| Viewer | `viewer@cadence.demo` / `password` | Read only |

All three are worth logging into — the permission model is part of the
project, not incidental to it.

## Services

| Service | Purpose |
|---|---|
| `web` | Django + gunicorn |
| `postgres` | PostgreSQL 16 |
| `redis` | Celery broker |
| `worker` | Celery worker |
| `beat` | Celery beat — nightly worklog snapshot |

## Commands

```bash
# Demo data
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py seed_demo --reset      # wipe first

# Burndown data (normally nightly via beat)
docker compose exec web python manage.py write_worklogs

# Tests
docker compose exec web pytest
docker compose exec web pytest tests/test_dependency_graph.py
```

## Configuration

`.env.example` documents every variable. No secret has a fallback default
— a missing `SECRET_KEY` fails loudly at startup rather than silently
running with something insecure.

```env
DEBUG=1
SECRET_KEY=...
ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgres://cadence:cadence@postgres:5432/cadence
CELERY_BROKER_URL=redis://redis:6379/0
```

`CSRF_TRUSTED_ORIGINS` is only needed in production, behind a proxy — see
[architecture.md](architecture.md) and `cadence/settings.py`'s
`if not DEBUG:` block, which turns on SSL redirect, secure cookies and HSTS
automatically once `DEBUG=0`.

## Notes

- The `beat` container needs to be running for burndown data to accumulate
  on its own; `write_worklogs` can be run by hand for a demo.
- `seed_demo` writes daily worklogs across the active sprint, so the
  burndown has real daily rows rather than two endpoints.
- After any change to the seeder, re-run it and confirm the cycle-rejection
  demo still reproduces — open task CAD-3, add a dependency on CAD-7, it
  should reject.
