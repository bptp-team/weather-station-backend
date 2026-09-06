.PHONY: sync dev

sync:
	pip install uv==0.12.10
	uv sync

dev:
	uv run fastapi dev app/main.py