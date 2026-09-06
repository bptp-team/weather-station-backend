from datetime import datetime, timedelta, timezone

import pytest

from app.mqtt.parser import parse_message
from app.repositories.influx import snapshot_to_point
from app.services.snapshot import SnapshotAggregator
from app.main import create_app


def test_parse_valid_temperature_message() -> None:
    event = parse_message(
        "weather/station-01/airTemperature",
        b"23.45",
        received_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )

    assert event.device_id == "station-01"
    assert event.measurement == "airTemperature"
    assert event.value == 23.45


def test_parse_rejects_unknown_measurement_and_invalid_payload() -> None:
    with pytest.raises(ValueError):
        parse_message("weather/station-01/unknown", b"1")

    with pytest.raises(ValueError):
        parse_message("weather/station-01/airTemperature", b"not-a-number")


def test_six_measurements_emit_one_complete_snapshot() -> None:
    aggregator = SnapshotAggregator(window=timedelta(seconds=30))
    timestamp = datetime(2026, 9, 6, tzinfo=timezone.utc)
    messages = (
        ("airTemperature", 23.45),
        ("airPressure", 101325.0),
        ("airHumidity", 45.0),
        ("daylight", "DAY"),
        ("waterLevel", 12),
        ("airQuality", 4),
    )

    snapshots = [
        aggregator.accept("station-01", measurement, value, timestamp)
        for measurement, value in messages
    ]

    incomplete_snapshots = snapshots[:-1]
    completed_snapshot = snapshots[-1]

    assert incomplete_snapshots == [None] * 5
    assert completed_snapshot.device_id == "station-01"
    assert completed_snapshot.air_temperature == 23.45


def test_incomplete_snapshot_expires_without_emitting() -> None:
    aggregator = SnapshotAggregator(window=timedelta(seconds=30))
    timestamp = datetime(2026, 9, 6, tzinfo=timezone.utc)

    assert aggregator.accept("station-01", "airTemperature", 23.45, timestamp) is None
    assert aggregator.expire(timestamp + timedelta(seconds=31)) == ["station-01"]


def test_snapshot_maps_to_influx_point() -> None:
    aggregator = SnapshotAggregator(window=timedelta(seconds=30))
    timestamp = datetime(2026, 9, 6, tzinfo=timezone.utc)

    for measurement, value in (
        ("airTemperature", 23.45),
        ("airPressure", 101325.0),
        ("airHumidity", 45.0),
        ("daylight", "DAY"),
        ("waterLevel", 12),
        ("airQuality", 4),
    ):
        snapshot = aggregator.accept("station-01", measurement, value, timestamp)

    point = snapshot_to_point(snapshot, measurement_name="weather_reading")

    assert point.measurement == "weather_reading"
    assert point.tags == {"device_id": "station-01"}
    assert point.fields["airTemperature"] == 23.45
    assert point.fields["daylight"] == "DAY"
    assert point.time == timestamp


def test_app_lifecycle_starts_and_stops_subscriber() -> None:
    lifecycle = []

    class FakeRepository:
        def close(self) -> None:
            lifecycle.append("repository.close")

    class FakeSubscriber:
        def start(self) -> None:
            lifecycle.append("subscriber.start")

        def stop(self) -> None:
            lifecycle.append("subscriber.stop")

    app = create_app(
        repository_factory=lambda settings: FakeRepository(),
        subscriber_factory=lambda settings, service: FakeSubscriber(),
        database_initializer=lambda settings: lifecycle.append("database.initialize"),
    )

    from fastapi.testclient import TestClient

    with TestClient(app):
        assert lifecycle == ["database.initialize", "subscriber.start"]

    assert lifecycle == [
        "database.initialize",
        "subscriber.start",
        "subscriber.stop",
        "repository.close",
    ]