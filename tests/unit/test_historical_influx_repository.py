from datetime import datetime, timedelta, timezone

import pyarrow as pa
import pytest

from app.repositories.historical_influx import HistoricalInfluxRepository


START = datetime(2026, 9, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 7, tzinfo=timezone.utc)


class FakeQueryResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def to_pylist(self) -> list[dict[str, object]]:
        return self.rows


class FakeInfluxClient:
    def __init__(self, result: FakeQueryResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def query(self, query: str, **kwargs: object) -> FakeQueryResult:
        self.calls.append({"query": query, **kwargs})
        return self.result


@pytest.fixture
def client() -> FakeInfluxClient:
    return FakeInfluxClient(FakeQueryResult([]))


@pytest.fixture
def repository(client: FakeInfluxClient) -> HistoricalInfluxRepository:
    return HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
    )


def test_read_queries_station_range_and_maps_all_measurements(
    client: FakeInfluxClient,
    repository: HistoricalInfluxRepository,
) -> None:
    client.result = FakeQueryResult(
        [
            {
                "time": datetime(2026, 9, 6, 10, tzinfo=timezone.utc),
                "device_id": "station-01",
                "air_temperature": 23.45,
                "air_pressure": 101325.0,
                "air_humidity": 45.0,
                "air_quality": 4,
                "daylight": 2748,
                "water_level": 12,
            }
        ]
    )
    snapshots = repository.read("station-01", START, END)

    assert snapshots[0].device_id == "station-01"
    assert snapshots[0].air_temperature == 23.45
    assert snapshots[0].air_pressure == 101325.0
    assert snapshots[0].air_humidity == 45.0
    assert snapshots[0].air_quality == 4
    assert snapshots[0].daylight == 2748
    assert snapshots[0].water_level == 12
    assert snapshots[0].received_at == datetime(2026, 9, 6, 10, tzinfo=timezone.utc)

    call = client.calls[0]
    assert call["database"] == "weather-station-db"
    assert call["language"] == "sql"
    assert call["mode"] == "all"
    assert call["query_parameters"] == {
        "station_id": "station-01",
        "start": START.isoformat(),
        "end": END.isoformat(),
    }
    assert 'FROM "weather_reading"' in call["query"]
    assert "device_id = $station_id" in call["query"]
    assert "time >= $start" in call["query"]
    assert "time < $end" in call["query"]


def test_read_returns_empty_result_without_rows(
    repository: HistoricalInfluxRepository,
) -> None:
    assert repository.read(
        "station-01",
        START,
        datetime(2026, 9, 2, tzinfo=timezone.utc),
    ) == []


def test_read_converts_arrow_nanosecond_timestamps_to_python_datetime() -> None:
    client = FakeInfluxClient(
        pa.table(
            {
                "time": pa.array(
                    [1789329373262545247],
                    type=pa.timestamp("ns"),
                ),
                "device_id": ["station-01"],
                "air_temperature": [23.45],
                "air_pressure": [101325.0],
                "air_humidity": [45.0],
                "air_quality": [4],
                "daylight": [2748],
                "water_level": [12],
            }
        )
    )
    repository = HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
    )

    snapshots = repository.read("station-01", START, END)

    expected_received_at = datetime(1970, 1, 1) + timedelta(
        microseconds=1789329373262545247 // 1_000
    )
    assert snapshots[0].received_at == expected_received_at
