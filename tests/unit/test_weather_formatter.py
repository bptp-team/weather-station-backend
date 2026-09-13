from datetime import datetime, timezone

from app.api.formatters.weather import snapshot_to_api_payload
from app.models.weather import WeatherSnapshot


def test_snapshot_to_api_payload_matches_public_snapshot_contract() -> None:
    snapshot = WeatherSnapshot(
        device_id="station-01",
        air_temperature=23.45,
        air_pressure=101325.0,
        air_humidity=45.0,
        air_quality=4,
        daylight=2748,
        water_level=12,
        received_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )

    assert snapshot_to_api_payload(snapshot) == {
        "device_id": "station-01",
        "air_temperature": 23.45,
        "air_pressure": 1.0,
        "air_humidity": 45.0,
        "air_quality": 4,
        "daylight": 2748,
        "water_level": 12,
        "received_at": "2026-09-06T00:00:00+00:00",
    }


def test_snapshot_to_api_payload_contains_no_datetime_values() -> None:
    snapshot = WeatherSnapshot(
        device_id="station-01",
        air_temperature=23.45,
        air_pressure=95000.0,
        air_humidity=45.0,
        air_quality=4,
        daylight=2748,
        water_level=12,
        received_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )

    payload = snapshot_to_api_payload(snapshot)

    assert all(not isinstance(value, datetime) for value in payload.values())
