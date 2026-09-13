from datetime import datetime, timezone

from app.repositories.historical_influx import HistoricalInfluxRepository


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


def test_read_queries_station_range_and_maps_all_measurements() -> None:
    client = FakeInfluxClient(
        FakeQueryResult(
            [
                {
                    "time": datetime(2026, 9, 6, 10, tzinfo=timezone.utc),
                    "device_id": "station-01",
                    "airTemperature": 23.45,
                    "airPressure": 101325.0,
                    "airHumidity": 45.0,
                    "airQuality": 4,
                    "daylight": 2748,
                    "waterLevel": 12,
                }
            ]
        )
    )
    repository = HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
    )
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 7, tzinfo=timezone.utc)

    snapshots = repository.read("station-01", start, end)

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
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    assert 'FROM "weather_reading"' in call["query"]
    assert "device_id = $station_id" in call["query"]
    assert "time >= $start" in call["query"]
    assert "time < $end" in call["query"]


def test_read_returns_empty_result_without_rows() -> None:
    client = FakeInfluxClient(FakeQueryResult([]))
    repository = HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
    )

    assert repository.read(
        "station-01",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 2, tzinfo=timezone.utc),
    ) == []
