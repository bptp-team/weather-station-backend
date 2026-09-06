import asyncio
import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.api.v1.routes.readings import _stream_snapshots, stream_readings
from app.models.weather import WeatherSnapshot
from app.services.broadcaster import SnapshotBroadcaster


def make_snapshot(
    device_id: str = "station-01",
    air_pressure: float = 101325.0,
) -> WeatherSnapshot:
    return WeatherSnapshot(
        device_id=device_id,
        air_temperature=23.45,
        air_pressure=air_pressure,
        air_humidity=45.0,
        air_quality=4,
        daylight=2748,
        water_level=12,
        received_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )


def test_subscriber_receives_future_snapshot_as_sse_data() -> None:
    broadcaster = SnapshotBroadcaster()
    subscription = broadcaster.subscribe()
    stream = _stream_snapshots(subscription)
    snapshot = make_snapshot()

    broadcaster.publish(snapshot)

    event = asyncio.run(stream.__anext__())

    assert event.startswith("data: ")
    assert json.loads(event.removeprefix("data: ").strip()) == {
        "device_id": "station-01",
        "air_temperature": 23.45,
        "air_pressure": 1.0,
        "air_humidity": 45.0,
        "air_quality": 4,
        "daylight": 2748,
        "water_level": 12,
        "received_at": "2026-09-06T00:00:00+00:00",
    }

    asyncio.run(stream.aclose())
    broadcaster.publish(make_snapshot("station-02"))


def test_snapshot_air_pressure_is_streamed_in_atm() -> None:
    broadcaster = SnapshotBroadcaster()
    subscription = broadcaster.subscribe()
    stream = _stream_snapshots(subscription)

    broadcaster.publish(make_snapshot(air_pressure=95000.0))

    event = asyncio.run(stream.__anext__())
    payload = json.loads(event.removeprefix("data: ").strip())

    assert payload["air_pressure"] == pytest.approx(0.937577, rel=1e-5)

    asyncio.run(stream.aclose())


def test_closed_broadcaster_ends_stream() -> None:
    broadcaster = SnapshotBroadcaster()
    subscription = broadcaster.subscribe()
    stream = _stream_snapshots(subscription)

    broadcaster.close()

    with pytest.raises(StopAsyncIteration):
        asyncio.run(stream.__anext__())


def test_stream_route_uses_event_stream_media_type() -> None:
    app = FastAPI()
    app.state.snapshot_broadcaster = SnapshotBroadcaster()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/readings/stream",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "app": app,
        }
    )

    response = asyncio.run(stream_readings(request))

    assert response.media_type == "text/event-stream"
    asyncio.run(response.body_iterator.aclose())