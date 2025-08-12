# Build
FROM python:3.12-slim AS builder
WORKDIR /app
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt requirements-dev.txt ./
RUN python -m pip install --upgrade pip && pip wheel --wheel-dir=/wheels -r requirements.txt

# Final
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY app ./app
EXPOSE 8000
CMD ["python", "-m", "app.main"]
