-include .env

UV_VERSION ?= 0.12.10

.PHONY: uv sync dev prod test

# Local bootstrap only: CI gets uv from the setup-uv action instead.
uv:
	pip install uv==$(UV_VERSION)

# Fails if uv.lock is out of date instead of silently re-resolving.
sync:
	uv sync --locked --all-extras --dev

dev:
	uv run fastapi dev app/main.py

prod:
	uv run fastapi run app/main.py --host 0.0.0.0 --port $(WEATHER_BACKEND_PORT) --workers 1

test:
	uv run pytest
