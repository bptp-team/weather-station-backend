from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes.historical_readings import router
from app.api.v1.routes.readings import _snapshot_to_event_payload
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


def test_history_returns_the_same_payload_as_streaming() -> None:
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
    assert response.json() == [_snapshot_to_event_payload(snapshot)]
    assert service.request == (
        "station-01",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 7, tzinfo=timezone.utc),
    )


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
