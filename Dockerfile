# syntax=docker/dockerfile:1

# Build
FROM python:3.12.14-slim-trixie AS build

# Package manager
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev

# Runtime
FROM python:3.12.14-slim-trixie AS runtime

# User
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONOPTIMIZE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies
COPY --from=build --chown=0:0 /app/.venv /app/.venv

# Source
COPY --chown=0:0 --chmod=u=rwX,go=rX app ./app

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["fastapi", "run", "app/main.py"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
