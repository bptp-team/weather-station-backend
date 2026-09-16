from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes.historical_readings import router
from app.models.weather import WeatherSnapshot


def make_snapshot() -> WeatherSnapshot:
    return WeatherSnapshot(
        device_id="station-01",
        air_temperature=23.456,
        air_pressure=101234.567,
        air_humidity=45.678,
        air_quality=4,
        daylight=2748,
        water_level=12,
        received_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )


class FakeHistoricalService:
    def __init__(self, snapshots: list[WeatherSnapshot]) -> None:
        self.snapshots = snapshots
        self.request: tuple[str, datetime | None, datetime | None] | None = None

    def read(
        self,
        station_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[WeatherSnapshot]:
        self.request = (station_id, start, end)
        return self.snapshots


def make_test_client(service: FakeHistoricalService) -> TestClient:
    app = FastAPI()
    app.state.historical_readings_service = service
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_history_returns_snapshots_with_interval_precipitation() -> None:
    snapshot = make_snapshot()
    service = FakeHistoricalService([snapshot])

    with make_test_client(service) as client:
        response = client.get(
            "/api/v1/readings/station-01",
            params={
                "from": "2026-09-01T00:00:00Z",
                "to": "2026-09-07T00:00:00Z",
            },
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "device_id": "station-01",
            "air_temperature": 23.46,
            "air_pressure": 1.0,
            "air_humidity": 45.68,
            "air_quality": 4,
            "daylight": 2748,
            "precipitation_interval": 0.0,
            "received_at": "2026-09-06T00:00:00+00:00",
        }
    ]
    assert service.request == (
        "station-01",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 7, tzinfo=timezone.utc),
    )


def test_history_sums_multiple_precipitation_intervals_for_one_day() -> None:
    baseline = replace(
        make_snapshot(),
        water_level=50,
        received_at=datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    first_rainfall = replace(
        baseline,
        water_level=150,
        received_at=baseline.received_at + timedelta(seconds=1),
    )
    second_rainfall = replace(
        baseline,
        water_level=225,
        received_at=baseline.received_at + timedelta(seconds=2),
    )
    service = FakeHistoricalService([baseline, first_rainfall, second_rainfall])

    with make_test_client(service) as client:
        response = client.get(
            "/api/v1/readings/station-01",
            params={
                "from": "2026-09-06T00:00:00Z",
                "to": "2026-09-07T00:00:00Z",
            },
        )

    # 10.0 mL in the first interval plus 8.75 mL in the second interval.
    assert response.status_code == 200
    readings = response.json()
    assert len(readings) == 3
    assert readings[-1]["air_temperature"] == 23.46
    assert readings[-1]["air_pressure"] == 1.0
    assert readings[-1]["precipitation_interval"] == round(8.75 / 4.42, 2)
    assert "water_level" not in readings[-1]
    assert "precipitation_accumulated" not in readings[-1]
    assert readings[-1]["received_at"] == "2026-09-06T12:00:02+00:00"


def test_history_returns_empty_list_when_no_snapshot_exists() -> None:
    service = FakeHistoricalService([])

    with make_test_client(service) as client:
        response = client.get("/api/v1/readings/station-01")

    assert response.status_code == 200
    assert response.json() == []


def test_history_rejects_only_one_date_parameter() -> None:
    service = FakeHistoricalService([])

    with make_test_client(service) as client:
        response = client.get(
            "/api/v1/readings/station-01",
            params={"from": "2026-09-01T00:00:00Z"},
        )

    assert response.status_code == 422
    assert "from and to must be provided together" in response.json()["detail"]


@pytest.mark.parametrize("parameter_name", ["from", "to"])
def test_history_rejects_injection_payload_in_date_parameter(parameter_name: str) -> None:
    service = FakeHistoricalService([])
    malicious_date = "2026-09-01T00:00:00Z' OR 1=1; DROP TABLE weather_reading; --"
    request_dates = {
        "from": "2026-09-01T00:00:00Z",
        "to": "2026-09-02T00:00:00Z",
    }
    request_dates[parameter_name] = malicious_date

    with make_test_client(service) as client:
        response = client.get(
            "/api/v1/readings/station-01",
            params=request_dates,
        )

    assert response.status_code == 422
    assert service.request is None
