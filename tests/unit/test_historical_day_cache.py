import os
from datetime import date, datetime, timezone

import pytest

import app.repositories.historical_cache as historical_cache_module
from app.repositories.historical_cache import SQLiteHistoricalDayCache


def test_cache_round_trips_rows_across_cache_instances(tmp_path) -> None:
    cache_path = tmp_path / "historical.sqlite3"
    day = date(2026, 9, 1)
    rows = [
        {
            "time": datetime(2026, 9, 1, 10, tzinfo=timezone.utc),
            "device_id": "station-01",
            "air_temperature": 23.45,
        }
    ]

    SQLiteHistoricalDayCache(cache_path).put("station-01", day, rows)

    cached_rows = SQLiteHistoricalDayCache(cache_path).get("station-01", day)

    assert cached_rows == [
        {
            "time": "2026-09-01T10:00:00+00:00",
            "device_id": "station-01",
            "air_temperature": 23.45,
        }
    ]


def test_cache_separates_station_and_utc_day(tmp_path) -> None:
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")
    day = date(2026, 9, 1)
    cache.put("station-01", day, [{"device_id": "station-01"}])

    assert cache.get("station-02", day) is None
    assert cache.get("station-01", date(2026, 9, 2)) is None


def test_cache_schema_version_invalidates_previous_rows(tmp_path, monkeypatch) -> None:
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")
    day = date(2026, 9, 1)
    cache.put("station-01", day, [{"device_id": "station-01"}])

    monkeypatch.setattr(historical_cache_module, "HISTORICAL_CACHE_SCHEMA_VERSION", 2)

    assert cache.get("station-01", day) is None


def test_cache_does_not_store_empty_days(tmp_path) -> None:
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")

    cache.put("station-01", date(2026, 9, 1), [])

    assert cache.get("station-01", date(2026, 9, 1)) is None


def test_cache_prunes_days_before_retention_cutoff(tmp_path) -> None:
    cache = SQLiteHistoricalDayCache(tmp_path / "historical.sqlite3")
    cache.put("station-01", date(2026, 9, 1), [{"device_id": "old"}])
    cache.put("station-01", date(2026, 9, 2), [{"device_id": "retained"}])

    cache.prune_before(date(2026, 9, 2))

    assert cache.get("station-01", date(2026, 9, 1)) is None
    assert cache.get("station-01", date(2026, 9, 2)) == [{"device_id": "retained"}]


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits are not available")
def test_cache_files_are_private_on_posix(tmp_path) -> None:
    cache_path = tmp_path / "private" / "historical.sqlite3"
    SQLiteHistoricalDayCache(cache_path)

    assert cache_path.parent.stat().st_mode & 0o777 == 0o700
    assert cache_path.stat().st_mode & 0o777 == 0o600
