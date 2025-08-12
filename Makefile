SHELL := /bin/bash

.PHONY: setup dev-up dev-down lint test

setup:
	pipx install pre-commit || pip install pre-commit
	pre-commit install

dev-up:
	docker compose up -d --build

dev-down:
	docker compose down -v

lint:
	pre-commit run -a

test:
	python -m pip install -r services/config-service/requirements-dev.txt
	pytest
