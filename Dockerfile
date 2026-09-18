# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.12.14-slim-trixie

FROM ${PYTHON_IMAGE} AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev

FROM ${PYTHON_IMAGE} AS runtime

RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=build /app/.venv /app/.venv
COPY --chmod=u=rwX,go=rX app ./app

USER app

EXPOSE 8000

CMD ["fastapi", "run", "app/main.py", "--port", "8000", "--workers", "1"]
