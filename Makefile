SHELL := /bin/bash

.PHONY: setup dev-up dev-down lint test e2e e2e-sh migrate-generate migrate-up migrate-down \
        web-dashboard-e2e

ALEMBIC_CONFIG ?= infra/migrations/alembic.ini
ALEMBIC_DATABASE_URL ?= postgresql+psycopg2://trading:trading@localhost:5432/trading
REVISION ?= head
DOWN_REVISION ?= -1

setup:
        pipx install pre-commit || pip install pre-commit
        pre-commit install

dev-up:
	docker compose up -d postgres redis
	docker compose up -d --build auth-service user-service

dev-down:
	docker compose down -v

lint:
	pre-commit run -a

test:
	python -m pip install -r requirements-dev.txt
	python -m pip install -r services/auth-service/requirements-dev.txt
	python -m pip install -r services/config-service/requirements-dev.txt
	python -m coverage erase
	python -m coverage run -m pytest
	python -m coverage xml
	python -m coverage html

e2e:
        pwsh -NoProfile -File ./scripts/e2e/auth_e2e.ps1

e2e-sh:
        bash ./scripts/e2e/auth_e2e.sh

web-dashboard-e2e:
        python -m pytest services/web-dashboard/tests/e2e

migrate-generate:
        @if [ -z "$(message)" ]; then \
                echo "Usage: make migrate-generate message=\"Add new table\""; \
                exit 1; \
        fi
        ALEMBIC_DATABASE_URL=$(ALEMBIC_DATABASE_URL) alembic -c $(ALEMBIC_CONFIG) revision --autogenerate -m "$(message)"

migrate-up:
        ALEMBIC_DATABASE_URL=$(ALEMBIC_DATABASE_URL) alembic -c $(ALEMBIC_CONFIG) upgrade $(REVISION)

migrate-down:
        ALEMBIC_DATABASE_URL=$(ALEMBIC_DATABASE_URL) alembic -c $(ALEMBIC_CONFIG) downgrade $(DOWN_REVISION)
