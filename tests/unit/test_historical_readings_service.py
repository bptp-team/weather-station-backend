from datetime import datetime, timedelta, timezone

import pytest

from app.models.weather import WeatherSnapshot
from app.services.historical_readings import (
    HistoricalReadingsService,
    InvalidReadingRange,
)


def make_snapshot(received_at: datetime) -> WeatherSnapshot:
    return WeatherSnapshot(
        device_id="station-01",
        air_temperature=23.45,
        air_pressure=101325.0,
        air_humidity=45.0,
        air_quality=4,
        daylight=2748,
        water_level=12,
        received_at=received_at,
    )


class FakeHistoricalRepository:
    def __init__(self, snapshots: list[WeatherSnapshot]) -> None:
        self.snapshots = snapshots
        self.request: tuple[str, datetime, datetime] | None = None

    def read(self, station_id: str, start: datetime, end: datetime) -> list[WeatherSnapshot]:
        self.request = (station_id, start, end)
        return self.snapshots


def test_reads_current_utc_day_when_dates_are_omitted() -> None:
    repository = FakeHistoricalRepository([])
    service = HistoricalReadingsService(
        repository,
        now=lambda: datetime(2026, 9, 13, 14, 30, tzinfo=timezone.utc),
    )

    assert service.read("station-01") == []
    assert repository.request == (
        "station-01",
        datetime(2026, 9, 13, tzinfo=timezone.utc),
        datetime(2026, 9, 14, tzinfo=timezone.utc),
    )


def test_reads_snapshots_in_chronological_order() -> None:
    older = make_snapshot(datetime(2026, 9, 6, 10, tzinfo=timezone.utc))
    newer = make_snapshot(datetime(2026, 9, 6, 11, tzinfo=timezone.utc))
    repository = FakeHistoricalRepository([newer, older])
    service = HistoricalReadingsService(repository)

    result = service.read(
        "station-01",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert result == [older, newer]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 9, 1, tzinfo=timezone.utc), None),
        (None, datetime(2026, 9, 2, tzinfo=timezone.utc)),
        (datetime(2026, 9, 2, tzinfo=timezone.utc), datetime(2026, 9, 1, tzinfo=timezone.utc)),
        (
            datetime(2026, 9, 1, tzinfo=timezone.utc),
            datetime(2026, 9, 17, tzinfo=timezone.utc),
        ),
        (datetime(2026, 9, 1), datetime(2026, 9, 2)),
    ],
)
def test_rejects_invalid_ranges(
    start: datetime | None,
    end: datetime | None,
) -> None:
    service = HistoricalReadingsService(FakeHistoricalRepository([]))

    with pytest.raises(InvalidReadingRange):
        service.read("station-01", start, end)


def test_accepts_exactly_fifteen_days() -> None:
    repository = FakeHistoricalRepository([])
    service = HistoricalReadingsService(repository)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=15)

    service.read("station-01", start, end)

    assert repository.request == ("station-01", start, end)
