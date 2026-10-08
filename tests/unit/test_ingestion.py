from datetime import datetime, timedelta, timezone

import pytest

from app.mqtt.parser import parse_message
from app.models.weather import MeasurementEvent, WeatherSnapshot
from app.repositories.influx import snapshot_to_point
from app.services.ingestion import WeatherIngestionService
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


def test_parse_valid_daylight_message() -> None:
    event = parse_message("weather/station-01/daylight", b"2748")

    assert event.measurement == "daylight"
    assert event.value == 2748
    assert isinstance(event.value, int)

@pytest.mark.parametrize(
    ("measurement", "payload", "expected"),
    [
        ("latitude", b"-23.20027778", -23.20027778),
        ("longitude", b"-45.89111111", -45.89111111),
    ],
)
def test_parse_valid_coordinate_messages(
    measurement: str,
    payload: bytes,
    expected: float,
) -> None:
    event = parse_message(f"weather/station-01/{measurement}", payload)

    assert event.measurement == measurement
    assert event.value == expected

@pytest.mark.parametrize(
    ("measurement", "payload"),
    [
        ("latitude", b"90.0001"),
        ("latitude", b"nan"),
        ("longitude", b"-180.0001"),
        ("longitude", b"inf"),
    ],
)
def test_parse_rejects_out_of_range_or_non_finite_coordinates(
    measurement: str,
    payload: bytes,
) -> None:
    with pytest.raises(ValueError, match="Invalid coordinate"):
        parse_message(f"weather/station-01/{measurement}", payload)


def test_parse_rejects_unknown_measurement_and_invalid_payload() -> None:
    with pytest.raises(ValueError):
        parse_message("weather/station-01/unknown", b"1")

    with pytest.raises(ValueError):
        parse_message("weather/station-01/airTemperature", b"not-a-number")

    with pytest.raises(ValueError):
        parse_message("weather/station-01/daylight", b"DAY")


def test_snapshot_waits_for_both_station_coordinates() -> None:
    aggregator = SnapshotAggregator(window=timedelta(seconds=30))
    timestamp = datetime(2026, 9, 6, tzinfo=timezone.utc)
    messages = (
        ("airTemperature", 23.45),
        ("airPressure", 101325.0),
        ("airHumidity", 45.0),
        ("daylight", 2748),
        ("waterLevel", 12),
        ("airQuality", 4),
        ("latitude", -23.20027778),
        ("longitude", -45.89111111),
    )

    snapshots = [
        aggregator.accept("station-01", measurement, value, timestamp)
        for measurement, value in messages
    ]

    incomplete_snapshots = snapshots[:-1]
    completed_snapshot = snapshots[-1]

    assert incomplete_snapshots == [None] * 7
    assert completed_snapshot.device_id == "station-01"
    assert completed_snapshot.air_temperature == 23.45
    assert completed_snapshot.latitude == -23.20027778
    assert completed_snapshot.longitude == -45.89111111


def test_incomplete_snapshot_expires_without_emitting() -> None:
    aggregator = SnapshotAggregator(window=timedelta(seconds=30))
    timestamp = datetime(2026, 9, 6, tzinfo=timezone.utc)

    assert aggregator.accept("station-01", "airTemperature", 23.45, timestamp) is None
    assert aggregator.expire(timestamp + timedelta(seconds=31)) == ["station-01"]


def test_ingestion_saves_complete_snapshot_before_publishing() -> None:
    lifecycle = []

    class FakeRepository:
        def save(self, snapshot) -> None:
            lifecycle.append(("save", snapshot))

    class FakeBroadcaster:
        def publish(self, snapshot) -> None:
            lifecycle.append(("publish", snapshot))

    service = WeatherIngestionService(
        FakeRepository(),
        window_seconds=30,
        broadcaster=FakeBroadcaster(),
    )
    timestamp = datetime(2026, 9, 6, tzinfo=timezone.utc)

    for measurement, value in (
        ("airTemperature", 23.456),
        ("airPressure", 101234.567),
        ("airHumidity", 45.678),
        ("daylight", 2748),
        ("waterLevel", 12),
        ("airQuality", 4),
        ("latitude", -23.20027778),
        ("longitude", -45.89111111),
    ):
        service.accept(MeasurementEvent("station-01", measurement, value, timestamp))

    assert [action for action, _ in lifecycle] == ["save", "publish"]
    assert lifecycle[0][1].device_id == lifecycle[1][1].device_id


def test_ingestion_does_not_publish_when_saving_fails() -> None:
    class FailingRepository:
        def save(self, snapshot) -> None:
            raise RuntimeError("database unavailable")

    class UnexpectedPublisher:
        def publish(self, snapshot) -> None:
            pytest.fail("snapshot was published before it was saved")

    service = WeatherIngestionService(
        FailingRepository(),
        window_seconds=30,
        broadcaster=UnexpectedPublisher(),
    )
    timestamp = datetime(2026, 9, 6, tzinfo=timezone.utc)

    with pytest.raises(RuntimeError, match="database unavailable"):
        for measurement, value in (
            ("airTemperature", 23.45),
            ("airPressure", 101325.0),
            ("airHumidity", 45.0),
            ("daylight", 2748),
            ("waterLevel", 12),
            ("airQuality", 4),
            ("latitude", -23.20027778),
            ("longitude", -45.89111111),
        ):
            service.accept(MeasurementEvent("station-01", measurement, value, timestamp))


def test_snapshot_maps_to_influx_point() -> None:
    aggregator = SnapshotAggregator(window=timedelta(seconds=30))
    timestamp = datetime(2026, 9, 6, tzinfo=timezone.utc)

    for measurement, value in (
        ("airTemperature", 23.456),
        ("airPressure", 101234.567),
        ("airHumidity", 45.678),
        ("daylight", 2748),
        ("waterLevel", 12),
        ("airQuality", 4),
        ("latitude", -23.20027778),
        ("longitude", -45.89111111),
    ):
        snapshot = aggregator.accept("station-01", measurement, value, timestamp)

    point = snapshot_to_point(snapshot, measurement_name="weather_reading")

    assert point.measurement == "weather_reading"
    assert point.tags == {"device_id": "station-01"}
    assert point.fields["air_temperature"] == 23.456
    assert point.fields["air_pressure"] == 101234.567
    assert point.fields["air_humidity"] == 45.678
    assert point.fields["daylight"] == 2748
    assert point.fields["water_level"] == 12
    assert point.fields["air_quality"] == 4
    assert point.fields["latitude"] == -23.20027778
    assert point.fields["longitude"] == -45.89111111
    assert isinstance(point.fields["air_temperature"], float)
    assert isinstance(point.fields["air_pressure"], float)
    assert isinstance(point.fields["air_humidity"], float)
    assert isinstance(point.fields["daylight"], int)
    assert isinstance(point.fields["water_level"], int)
    assert isinstance(point.fields["air_quality"], int)
    assert isinstance(point.fields["latitude"], float)
    assert isinstance(point.fields["longitude"], float)
    assert point.time == timestamp


def test_snapshot_without_both_coordinates_cannot_be_saved() -> None:
    snapshot = WeatherSnapshot(
        device_id="station-01",
        air_temperature=23.456,
        air_pressure=101234.567,
        air_humidity=45.678,
        air_quality=4,
        daylight=2748,
        water_level=12,
        received_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        latitude=-23.20027778,
    )

    with pytest.raises(ValueError, match="Both station coordinates"):
        snapshot_to_point(snapshot, measurement_name="weather_reading")


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
    )

    from fastapi.testclient import TestClient

    with TestClient(app):
        assert lifecycle == ["subscriber.start"]

    assert lifecycle == [
        "subscriber.start",
        "subscriber.stop",
        "repository.close",
    ]