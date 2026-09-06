from datetime import timedelta

from app.models.weather import MeasurementEvent
from app.repositories.influx import SnapshotRepository
from app.services.snapshot import SnapshotAggregator


class WeatherIngestionService:
    def __init__(self, repository: SnapshotRepository, *, window_seconds: int) -> None:
        self._repository = repository
        self._aggregator = SnapshotAggregator(window=timedelta(seconds=window_seconds))

    def accept(self, event: MeasurementEvent) -> None:
        snapshot = self._aggregator.accept(
            event.device_id,
            event.measurement,
            event.value,
            event.received_at,
        )
        
        if snapshot is not None:
            self._repository.save(snapshot)

    def expire(self, now) -> list[str]:
        return self._aggregator.expire(now)