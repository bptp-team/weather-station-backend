from datetime import datetime, timezone

import pytest

from app.repositories.historical_influx import HistoricalInfluxRepository


START = datetime(2026, 9, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 2, tzinfo=timezone.utc)


class FakeQueryResult:
    def to_pylist(self) -> list[dict[str, object]]:
        return []


class RecordingInfluxClient:
    def __init__(self) -> None:
        self.query_text = ""
        self.query_kwargs: dict[str, object] = {}

    def query(self, query: str, **kwargs: object) -> FakeQueryResult:
        self.query_text = query
        self.query_kwargs = kwargs
        return FakeQueryResult()


@pytest.fixture
def client() -> RecordingInfluxClient:
    return RecordingInfluxClient()


@pytest.fixture
def repository(client: RecordingInfluxClient) -> HistoricalInfluxRepository:
    return HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name="weather_reading",
    )


def read_with(repository: HistoricalInfluxRepository, station_id: str) -> None:
    repository.read(station_id, START, END)


def test_station_id_injection_payload_is_not_interpolated_into_sql(
    client: RecordingInfluxClient,
    repository: HistoricalInfluxRepository,
) -> None:
    malicious_station_id = 'station-01" OR 1=1; DROP TABLE weather_reading; --'

    read_with(repository, malicious_station_id)

    assert malicious_station_id not in client.query_text
    assert client.query_kwargs["query_parameters"] == {
        "station_id": malicious_station_id,
        "start": "2026-09-01T00:00:00+00:00",
        "end": "2026-09-02T00:00:00+00:00",
    }


def test_date_values_are_not_interpolated_into_sql(
    client: RecordingInfluxClient,
    repository: HistoricalInfluxRepository,
) -> None:
    read_with(repository, "station-01")

    assert "2026-09-01" not in client.query_text
    assert "2026-09-02" not in client.query_text


def test_measurement_name_quotes_are_escaped_as_one_identifier(
    client: RecordingInfluxClient,
) -> None:
    malicious_measurement = 'weather_reading"; DROP TABLE readings; --'
    repository = HistoricalInfluxRepository(
        client,
        database="weather-station-db",
        measurement_name=malicious_measurement,
    )

    read_with(repository, "station-01")

    escaped_measurement_name = malicious_measurement.replace('"', '""')
    expected_from_clause = f'FROM "{escaped_measurement_name}"'

    assert expected_from_clause in client.query_text
    assert 'FROM "weather_reading"; DROP TABLE readings; --"' not in client.query_text
