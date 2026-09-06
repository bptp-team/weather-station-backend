"""Application entry point: builds the app and wires the ingestion lifecycle.

Deliberately thin — no business rules here. Run with:
    make dev
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.settings import Settings
from app.db.influx import create_influx_client, ensure_database_exists
from app.mqtt.client import MqttSubscriber
from app.repositories.influx import InfluxRepository
from app.services.ingestion import WeatherIngestionService


def _configure_logging() -> None:
    application_logger = logging.getLogger("app")
    application_logger.setLevel(logging.INFO)
    application_logger.propagate = False

    if not application_logger.handlers:
        log_handler = logging.StreamHandler()
        log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        application_logger.addHandler(log_handler)


_configure_logging()


def _create_repository(settings: Settings) -> InfluxRepository:
    return InfluxRepository(
        create_influx_client(settings),
        database=settings.influx_database,
        measurement_name=settings.influx_measurement,
    )


def _create_subscriber(settings: Settings, service: WeatherIngestionService) -> MqttSubscriber:
    return MqttSubscriber(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        topic=settings.mqtt_topic,
        client_id=settings.mqtt_client_id,
        on_event=service.accept,
    )


def create_app(
    *,
    settings: Settings | None = None,
    repository_factory: Callable | None = None,
    subscriber_factory: Callable | None = None,
    database_initializer: Callable | None = None,
) -> FastAPI:
    """Application factory: lets the tests build an isolated app instance."""
    app_settings = settings or Settings()
    make_repository = repository_factory or _create_repository
    make_subscriber = subscriber_factory or _create_subscriber
    initialize_database = database_initializer or ensure_database_exists

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await asyncio.to_thread(initialize_database, app_settings)

        repository = make_repository(app_settings)
        service = WeatherIngestionService(
            repository,
            window_seconds=app_settings.snapshot_window_seconds,
        )
        subscriber = make_subscriber(app_settings, service)

        await asyncio.to_thread(subscriber.start)

        try:
            yield
        finally:
            await asyncio.to_thread(subscriber.stop)
            close = getattr(repository, "close", None)

            if close is not None:
                await asyncio.to_thread(close)

    app = FastAPI(title="Weather Station Back-end", lifespan=lifespan)

    # app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_app()
