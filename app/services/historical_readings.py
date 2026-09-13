from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.models.weather import WeatherSnapshot


MAX_READING_RANGE = timedelta(days=15)


class HistoricalReadRepository(Protocol):
    def read(self, station_id: str, start: datetime, end: datetime) -> list[WeatherSnapshot]:
        """Return complete snapshots in the half-open [start, end) interval."""


class InvalidReadingRange(ValueError):
    """Raised when a historical readings interval is invalid."""


class HistoricalReadingsService:
    def __init__(
        self,
        repository: HistoricalReadRepository,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._now = now or (lambda: datetime.now(timezone.utc))

    def read(
        self,
        station_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[WeatherSnapshot]:
        start, end = self._resolve_range(start, end)
        snapshots = self._repository.read(station_id, start, end)
        return sorted(snapshots, key=lambda snapshot: snapshot.received_at)

    def _resolve_range(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime, datetime]:
        if start is None and end is None:
            current = self._now()
            self._require_aware(current)
            current = current.astimezone(timezone.utc)
            start = current.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif start is None or end is None:
            raise InvalidReadingRange("from and to must be provided together")
        else:
            self._require_aware(start)
            self._require_aware(end)
            start = start.astimezone(timezone.utc)
            end = end.astimezone(timezone.utc)

        if end <= start:
            raise InvalidReadingRange("to must be after from")
        if end - start > MAX_READING_RANGE:
            raise InvalidReadingRange("the reading range cannot exceed 15 days")
        return start, end

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise InvalidReadingRange("dates must include a timezone")
