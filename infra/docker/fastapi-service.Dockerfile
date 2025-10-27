# syntax=docker/dockerfile:1
FROM python:3.12-slim

ARG SERVICE_DIR
ARG SERVICE_PACKAGE
ARG SERVICE_MODULE="app.main"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install service requirements if present
COPY services/${SERVICE_DIR}/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && if [ -s /tmp/requirements.txt ]; then pip install -r /tmp/requirements.txt; fi \
    && rm -f /tmp/requirements.txt

# Copy shared libraries and service source code
COPY libs ./libs
COPY providers ./providers
COPY schemas ./schemas
COPY infra ./infra
COPY scripts ./scripts
COPY services/${SERVICE_DIR} /app/service/${SERVICE_PACKAGE}

ENV PYTHONPATH="/app/service:/app" \
    RUN_MIGRATIONS=1

RUN chmod +x ./scripts/run_migrations.sh

CMD ["bash", "-c", "if [ \"${RUN_MIGRATIONS:-1}\" = \"1\" ]; then ./scripts/run_migrations.sh || exit 1; fi; exec uvicorn ${SERVICE_PACKAGE}.${SERVICE_MODULE}:app --host 0.0.0.0 --port 8000"]
