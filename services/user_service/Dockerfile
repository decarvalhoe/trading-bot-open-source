FROM python:3.12-slim
WORKDIR /app

COPY services/user_service/requirements.txt services/user_service/requirements-dev.txt ./
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

COPY libs ./libs
COPY infra ./infra
COPY scripts ./scripts
COPY services/user_service/app ./app

RUN chmod +x ./scripts/run_migrations.sh

ENV PYTHONPATH=/app
CMD ["bash","-c","./scripts/run_migrations.sh && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
