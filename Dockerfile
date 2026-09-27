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

# collectstatic needs SECRET_KEY/DATABASE_URL-shaped settings to import,
# but doesn't touch the database — a build-time-only dummy value is fine
# since the runtime container gets the real SECRET_KEY from Cloud Run env vars.
RUN SECRET_KEY=build-time-only-not-used-at-runtime \
    DATABASE_URL=postgresql://build:time@localhost:5432/build \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "cadence.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
