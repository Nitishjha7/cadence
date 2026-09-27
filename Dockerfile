FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic imports settings.py, which reads SECRET_KEY/DATABASE_URL/
# CELERY_BROKER_URL with no defaults — it never connects to either service,
# so build-time-only dummy values are fine; the runtime container gets the
# real ones from Cloud Run env vars.
RUN SECRET_KEY=build-time-only-not-used-at-runtime \
    DATABASE_URL=postgresql://build:time@localhost:5432/build \
    CELERY_BROKER_URL=redis://localhost:6379/0 \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "cadence.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
