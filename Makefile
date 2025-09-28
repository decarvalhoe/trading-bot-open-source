SHELL := /bin/bash

.PHONY: setup dev-up dev-down lint test e2e e2e-sh

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
