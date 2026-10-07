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
        query_parameters = kwargs.get("query_parameters")
        if (
            isinstance(self.result, FakeQueryResult)
            and isinstance(query_parameters, dict)
            and "start" in query_parameters
        ):
            start = datetime.fromisoformat(query_parameters["start"])
            end = datetime.fromisoformat(query_parameters["end"])
            return FakeQueryResult(
                [
                    row
                    for row in self.result.rows
                    if start <= row["time"] < end
                ]
            )
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
                "time": datetime(2026, 9, 1, 10, tzinfo=timezone.utc),
                "device_id": "station-01",
                "air_temperature": 23.45,
                "air_pressure": 101325.0,
                "air_humidity": 45.0,
                "air_quality": 4,
                "daylight": 2748,
                "water_level": 12,
                "latitude": -23.20027778,
                "longitude": -45.89111111,
            }
        ]
    )
    end = START + timedelta(days=1)
    snapshots = repository.read("station-01", START, end)

    assert snapshots[0].device_id == "station-01"
    assert snapshots[0].air_temperature == 23.45
    assert snapshots[0].air_pressure == 101325.0
    assert snapshots[0].air_humidity == 45.0
    assert snapshots[0].air_quality == 4
    assert snapshots[0].daylight == 2748
    assert snapshots[0].water_level == 12
    assert snapshots[0].latitude == -23.20027778
    assert snapshots[0].longitude == -45.89111111
    assert snapshots[0].received_at == datetime(2026, 9, 1, 10, tzinfo=timezone.utc)

    call = client.calls[0]
    assert call["database"] == "weather-station-db"
    assert call["language"] == "sql"
    assert call["mode"] == "all"
    assert call["query_parameters"] == {
        "station_id": "station-01",
        "start": START.isoformat(),
        "end": end.isoformat(),
    }
    assert 'FROM "weather_reading"' in call["query"]
    assert "device_id = $station_id" in call["query"]
    assert "time >= $start" in call["query"]
    assert "time < $end" in call["query"]
    assert "latitude" in call["query"]
    assert "longitude" in call["query"]


def test_read_queries_each_utc_day_sequentially_and_combines_results(
    client: FakeInfluxClient,
    repository: HistoricalInfluxRepository,
) -> None:
    first_start = datetime(2026, 9, 1, 18, tzinfo=timezone.utc)
    first_day = datetime(2026, 9, 1, tzinfo=timezone.utc)
    middle_start = datetime(2026, 9, 2, tzinfo=timezone.utc)
    last_start = datetime(2026, 9, 3, tzinfo=timezone.utc)
    end = datetime(2026, 9, 3, 6, tzinfo=timezone.utc)
    last_day_end = datetime(2026, 9, 4, tzinfo=timezone.utc)
    client.result = FakeQueryResult(
        [
            {
                "time": received_at,
                "device_id": "station-01",
                "air_temperature": 23.45,
                "air_pressure": 101325.0,
                "air_humidity": 45.0,
                "air_quality": 4,
                "daylight": 2748,
                "water_level": 12,
                "latitude": -23.20027778,
                "longitude": -45.89111111,
            }
            for received_at in (
                datetime(2026, 9, 1, 17, 59, tzinfo=timezone.utc),
                datetime(2026, 9, 1, 19, tzinfo=timezone.utc),
                datetime(2026, 9, 2, tzinfo=timezone.utc),
                datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
                datetime(2026, 9, 3, tzinfo=timezone.utc),
                end,
                datetime(2026, 9, 3, 7, tzinfo=timezone.utc),
            )
        ]
    )

    snapshots = repository.read("station-01", first_start, end)

    assert [snapshot.received_at for snapshot in snapshots] == [
        datetime(2026, 9, 1, 19, tzinfo=timezone.utc),
        datetime(2026, 9, 2, tzinfo=timezone.utc),
        datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
        datetime(2026, 9, 3, tzinfo=timezone.utc),
    ]
    assert [
        call["query_parameters"]
        for call in client.calls
    ] == [
        {
            "station_id": "station-01",
            "start": first_day.isoformat(),
            "end": middle_start.isoformat(),
        },
        {
            "station_id": "station-01",
            "start": middle_start.isoformat(),
            "end": last_start.isoformat(),
        },
        {
            "station_id": "station-01",
            "start": last_start.isoformat(),
            "end": last_day_end.isoformat(),
        },
    ]


def test_read_rejects_rows_without_backfilled_station_coordinates(
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

    with pytest.raises(ValueError, match="coordinates must be backfilled"):
        repository.read("station-01", START, END)


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
                "latitude": [-23.20027778],
                "longitude": [-45.89111111],
            }
        )
    )
    repository = HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
    )

    expected_received_at = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        microseconds=1789329373262545247 // 1_000
    )
    snapshots = repository.read(
        "station-01",
        expected_received_at,
        expected_received_at + timedelta(microseconds=1),
    )

    assert snapshots[0].received_at == expected_received_at
