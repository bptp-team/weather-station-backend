"""Application entry point: builds the app and wires the routers together.

Deliberately thin — no business rules here. Run with:
    uv run fastapi dev app/main.py
"""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Application factory: lets the tests build an isolated app instance."""
    app = FastAPI(title="Weather Station Back-end")

    # app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_app()
