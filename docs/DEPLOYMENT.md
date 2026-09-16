# Deployment — Railway + Neon

Goal: **one public URL** in the README that an interviewer can click, log in as
any of the three roles, and use — without installing anything.

> Nothing is deployed yet. This is written ahead of Phase 6 so the decisions are
> made before the pressure of "just get it online". It will be corrected against
> reality once the first deploy happens.

---

## What is left

- [ ] Create the Neon database (Step 1)
- [ ] Create the Railway project and connect the repo (Step 2)
- [ ] Set environment variables (Step 3)
- [ ] Migrate, seed, create the superuser (Step 4)
- [ ] Verify the five screens, all three logins, and the cycle demo (Step 5)
- [ ] Put the live URL and the three demo logins in the README

---

## Why Railway, not Render or PythonAnywhere

This app needs **three processes**: web, a Celery worker, and Celery beat. That is
the deciding constraint.

| | Railway | Render free | PythonAnywhere free |
|---|---|---|---|
| Multiple processes | Yes, one service each | Free tier is web only | No background workers |
| Sleeps when idle | No | **Yes, after 15 min** | No, but limited CPU |
| Postgres | External (Neon) | Free tier **expires after 90 days** | MySQL only on free |
| Cost | ~$5/month credit covers this | Free | Free |

**The sleeping rules out Render's free tier.** An interviewer clicking a link and
waiting 40 seconds for a cold start has already formed an opinion. And with no
beat process the nightly worklog snapshot never runs — so the burndown stops
accumulating, which is one of the five screens.

**Database on Neon, not Railway.** Free Postgres on most platforms expires —
Render's after 90 days — which would silently kill the portfolio link months after
it was last looked at. Neon's free tier does not expire.

---

## Architecture

```
                    Railway project
   +-----------------------------------------------+
   |                                               |
   |   web       gunicorn + whitenoise (public URL)|
   |   worker    celery -A cadence worker          |
   |   beat      celery -A cadence beat            |
   |   redis     Railway plugin                    |
   |                                               |
   +-----------------------------------------------+
                          |
                          v
                    Neon Postgres
```

Three services from **one image**, differing only in start command.

---

## Step 1 — Database (Neon)

1. [neon.tech](https://neon.tech) → new project → region closest to you
2. Copy the connection string; it must end with `?sslmode=require`

```
postgresql://user:pass@ep-xxx.ap-southeast-1.aws.neon.tech/cadence?sslmode=require
```

Neon suspends compute when idle and wakes on the next query — about a second,
invisible in a demo.

---

## Step 2 — Railway services

New project → Deploy from GitHub repo. Add two more services **from the same
repo**, overriding the start command:

| Service | Start command |
|---|---|
| `web` | `gunicorn cadence.wsgi:application --bind 0.0.0.0:$PORT` |
| `worker` | `celery -A cadence worker -l info` |
| `beat` | `celery -A cadence beat -l info` |

Add the **Redis** plugin. Railway injects `REDIS_URL` into every service.

### Beat is not optional

Without it, `write_worklogs` never runs and the burndown flatlines at whatever the
seeder wrote. The chart is one of the five demo screens, and it dies quietly —
the page still renders, it just stops telling the truth.

---

## Step 3 — Environment variables

Set on **all three** services:

```env
SECRET_KEY=...                  # 50+ random chars, no default anywhere in settings
DEBUG=0
ALLOWED_HOSTS=cadence.up.railway.app
CSRF_TRUSTED_ORIGINS=https://cadence.up.railway.app

DATABASE_URL=postgresql://...?sslmode=require
CELERY_BROKER_URL=${{Redis.REDIS_URL}}

DJANGO_SETTINGS_MODULE=cadence.settings.production
SECURE_SSL_REDIRECT=1
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
```

**`DEBUG=0` matters most.** Django's debug page prints settings and a full
traceback on any unhandled exception. On a public URL that is an information leak,
and `ALLOWED_HOSTS` is not enforced while `DEBUG=1`.

**`CSRF_TRUSTED_ORIGINS` is required on Django 4+** behind a proxy. Without it
every form POST fails with a CSRF error while the pages themselves render fine —
which makes the whole app look broken in exactly the interaction the demo depends
on (the dependency form).

**No secret has a fallback.** A missing `SECRET_KEY` must raise at startup, not
silently run with a default. A deployment that boots with an insecure key is worse
than one that refuses to boot.

---

## Step 4 — Migrate, seed, superuser

```bash
railway run --service web python manage.py migrate
railway run --service web python manage.py seed_demo
railway run --service web python manage.py createsuperuser
```

`seed_demo` creates the three role logins. The superuser is separate — it is for
the Django admin, which is the manager console and worth showing.

### Reseeding later

```bash
railway run --service web python manage.py seed_demo --reset
```

> **Set a reminder to reseed before interviews.** A sprint seeded as "active" in
> September is long finished by December, and a burndown that ended months ago
> makes the demo look abandoned. Dates are the detail people notice.

**After every reseed, verify the cycle demo still reproduces** — the two tasks
used in [DEMO_SCRIPT.md](DEMO_SCRIPT.md) §2 must still trigger the rejection.

---

## Static files

Whitenoise, not S3. `collectstatic` runs at build time; whitenoise serves from
the image with compression and cache headers.

S3 would be the right answer for user uploads at scale. There are no uploads here,
and adding a bucket to serve a few CSS files is infrastructure with nothing behind
it.

---

## Step 5 — Verify

Not "the page loads". Verify what the demo depends on:

- [ ] Board renders 45 seeded tasks, blocked ones greyed with lock icons
- [ ] **The cycle rejection fires** and names the actual path — the core demo
- [ ] Marking the blocking task done unblocks the dependent
- [ ] Capacity screen shows the member on leave at reduced hours
- [ ] Burndown renders with the scope-creep step visible
- [ ] **All three logins work** and see different things:
  - viewer cannot create a task
  - contributor cannot start a sprint
  - manager can
- [ ] `/admin/` reachable and manager-only
- [ ] Worker logs show tasks processed; beat logs show the daily tick

---

## Migrations on deploy — deliberately not automatic

Three services from one image would all run migrations on the same deploy.
Django's migration table prevents duplicate application, but three processes
racing the same lock is a failure mode with no upside on a project deployed by
hand a few times a month.

Migrations run explicitly in Step 4. A real pipeline would use a one-off release
job — not a race.

---

## Cost

| | |
|---|---|
| Railway | ~$5/month credit; three small services and Redis fit inside it |
| Neon | Free tier, does not expire |

If the credit runs out, take the link down rather than leave a dead URL in the
README. **A broken demo link is worse than no link.**

---

## Troubleshooting

**CSRF verification failed on every form** — `CSRF_TRUSTED_ORIGINS` missing or
missing the `https://` scheme. The most likely first failure, and it looks like
the app is broken rather than misconfigured.

**DisallowedHost** — `ALLOWED_HOSTS` does not include the Railway domain.

**Static files 404 with `DEBUG=0`** — `collectstatic` did not run at build, or
whitenoise is missing from `MIDDLEWARE`. Everything works locally with `DEBUG=1`
and breaks only in production, which is why Step 5 checks it.

**Database connection refused** — `?sslmode=require` missing from the Neon URL.

**Burndown stops updating** — beat is not running. The page still renders, so
nothing looks wrong until the dates are read closely.

**Board is slow** — the `is_blocked` N+1 has returned. `prefetch_related` was lost
somewhere; the query-count test in [TEST_PLAN.md](TEST_PLAN.md) §6 should have
caught it, so check that it still runs in CI.

---

## After deploying

- [ ] Live URL + all three demo logins at the top of the README
- [ ] **Real screenshots** replacing the ASCII sketches in [UI_FLOW.md](UI_FLOW.md)
- [ ] Remove the "not built yet" banner from the README
- [ ] README test counts taken from the actual run, not estimated
- [ ] Add a `DECISIONS.md` entry for anything that surprised you here — the CSRF
      one in particular is a specific, true story worth being able to tell
