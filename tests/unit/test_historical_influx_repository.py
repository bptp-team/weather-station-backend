from datetime import datetime, timedelta, timezone

import pyarrow as pa
import pytest

from app.repositories.historical_cache import SQLiteHistoricalDayCache
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


def test_read_reuses_completed_day_cache_for_overlapping_partial_ranges(
    tmp_path,
) -> None:
    client = FakeInfluxClient(
        FakeQueryResult(
            [
                {
                    "time": datetime(2026, 9, 8, hour, tzinfo=timezone.utc),
                    "device_id": "station-01",
                    "air_temperature": float(hour),
                    "air_pressure": 101325.0,
                    "air_humidity": 45.0,
                    "air_quality": 4,
                    "daylight": 2748,
                    "water_level": 12,
                    "latitude": -23.2,
                    "longitude": -45.89,
                }
                for hour in (10, 12)
            ]
        )
    )
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")
    repository = HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
        cache=cache,
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )

    first_range = repository.read(
        "station-01",
        datetime(2026, 9, 8, 9, tzinfo=timezone.utc),
        datetime(2026, 9, 8, 11, tzinfo=timezone.utc),
    )
    second_range = repository.read(
        "station-01",
        datetime(2026, 9, 8, 11, tzinfo=timezone.utc),
        datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
    )

    assert [snapshot.air_temperature for snapshot in first_range] == [10.0]
    assert [snapshot.air_temperature for snapshot in second_range] == [12.0]
    assert len(client.calls) == 1


def test_warm_cache_response_matches_direct_influx_response_for_partial_multi_day_range(
    tmp_path,
) -> None:
    source_rows = [
        {
            "time": datetime(2026, 9, day, hour, tzinfo=timezone.utc),
            "device_id": "station-01",
            "air_temperature": float(day * 24 + hour),
            "air_pressure": 101325.0,
            "air_humidity": 45.0,
            "air_quality": 4,
            "daylight": 2748,
            "water_level": 12,
            "latitude": -23.2,
            "longitude": -45.89,
        }
        for day, hour in ((8, 3), (8, 6), (8, 23), (9, 0), (9, 12), (10, 0), (10, 18), (10, 23))
    ]
    start = datetime(2026, 9, 8, 6, tzinfo=timezone.utc)
    end = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = lambda: datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")
    cache_client = FakeInfluxClient(FakeQueryResult(source_rows))
    cached_repository = HistoricalInfluxRepository(
        cache_client,
        database="weather-station-db",
        measurement_name="weather_reading",
        cache=cache,
        now=now,
    )

    cached_repository.read("station-01", start, end)
    cached_client = FakeInfluxClient(FakeQueryResult(source_rows))
    warm_cached_repository = HistoricalInfluxRepository(
        cached_client,
        database="weather-station-db",
        measurement_name="weather_reading",
        cache=cache,
        now=now,
    )
    uncached_client = FakeInfluxClient(FakeQueryResult(source_rows))
    uncached_repository = HistoricalInfluxRepository(
        uncached_client,
        database="weather-station-db",
        measurement_name="weather_reading",
        now=now,
    )

    warm_cached_result = warm_cached_repository.read("station-01", start, end)
    direct_result = uncached_repository.read("station-01", start, end)

    assert warm_cached_result == direct_result
    assert [snapshot.received_at for snapshot in direct_result] == [
        datetime(2026, 9, 8, 6, tzinfo=timezone.utc),
        datetime(2026, 9, 8, 23, tzinfo=timezone.utc),
        datetime(2026, 9, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 9, 12, tzinfo=timezone.utc),
        datetime(2026, 9, 10, 0, tzinfo=timezone.utc),
    ]
    assert cached_client.calls == []
    assert len(uncached_client.calls) == 3


def test_cache_entries_are_isolated_by_measurement(tmp_path) -> None:
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")
    now = lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    day_start = datetime(2026, 9, 8, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    row = {
        "time": datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
        "device_id": "station-01",
        "air_temperature": 10.0,
        "air_pressure": 101325.0,
        "air_humidity": 45.0,
        "air_quality": 4,
        "daylight": 2748,
        "water_level": 12,
        "latitude": -23.2,
        "longitude": -45.89,
    }
    first_client = FakeInfluxClient(FakeQueryResult([row]))
    first_repository = HistoricalInfluxRepository(
        first_client,
        database="weather-station-db",
        measurement_name="weather_reading",
        cache=cache,
        now=now,
    )
    first_repository.read("station-01", day_start, day_end)

    other_measurement_client = FakeInfluxClient(
        FakeQueryResult([{**row, "air_temperature": 12.0}])
    )
    other_measurement_repository = HistoricalInfluxRepository(
        other_measurement_client,
        database="weather-station-db",
        measurement_name="other_measurement",
        cache=cache,
        now=now,
    )

    snapshots = other_measurement_repository.read("station-01", day_start, day_end)

    assert [snapshot.air_temperature for snapshot in snapshots] == [12.0]
    assert len(other_measurement_client.calls) == 1


def test_read_does_not_cache_the_current_utc_day(tmp_path) -> None:
    client = FakeInfluxClient(
        FakeQueryResult(
            [
                {
                    "time": datetime(2026, 9, 10, 10, tzinfo=timezone.utc),
                    "device_id": "station-01",
                    "air_temperature": 10.0,
                    "air_pressure": 101325.0,
                    "air_humidity": 45.0,
                    "air_quality": 4,
                    "daylight": 2748,
                    "water_level": 12,
                    "latitude": -23.2,
                    "longitude": -45.89,
                }
            ]
        )
    )
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")
    repository = HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
        cache=cache,
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )
    today_start = datetime(2026, 9, 10, tzinfo=timezone.utc)
    tomorrow = today_start + timedelta(days=1)

    repository.read("station-01", today_start, tomorrow)
    repository.read("station-01", today_start, tomorrow)

    assert len(client.calls) == 2
    assert cache.get("station-01", today_start.date()) is None


def test_read_does_not_return_cached_rows_past_retention_cutoff(tmp_path) -> None:
    client = FakeInfluxClient(FakeQueryResult([]))
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")
    cache.put(
        "station-01",
        datetime(2026, 9, 8).date(),
        [
            {
                "time": datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
                "device_id": "station-01",
                "air_temperature": 10.0,
                "air_pressure": 101325.0,
                "air_humidity": 45.0,
                "air_quality": 4,
                "daylight": 2748,
                "water_level": 12,
                "latitude": -23.2,
                "longitude": -45.89,
            },
            {
                "time": datetime(2026, 9, 8, 13, tzinfo=timezone.utc),
                "device_id": "station-01",
                "air_temperature": 13.0,
                "air_pressure": 101325.0,
                "air_humidity": 45.0,
                "air_quality": 4,
                "daylight": 2748,
                "water_level": 12,
                "latitude": -23.2,
                "longitude": -45.89,
            },
        ],
        namespace='["weather-station-db","weather_reading"]',
    )
    repository = HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
        cache=cache,
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
        retention_days=2,
    )

    snapshots = repository.read(
        "station-01",
        datetime(2026, 9, 8, tzinfo=timezone.utc),
        datetime(2026, 9, 9, tzinfo=timezone.utc),
    )

    assert [snapshot.air_temperature for snapshot in snapshots] == [13.0]
    assert client.calls == []


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
