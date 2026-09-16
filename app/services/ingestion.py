from collections.abc import Callable
from datetime import timedelta

from app.models.weather import MeasurementEvent
from app.services.snapshot import SnapshotAggregator
from app.repositories.influx import SnapshotRepository
from app.services.broadcaster import SnapshotBroadcaster
from app.utils.precipitation import PrecipitationTracker


class WeatherIngestionService:
    def __init__(
        self,
        repository: SnapshotRepository,
        *,
        window_seconds: int,
        broadcaster: SnapshotBroadcaster | None = None,
        precipitation_tracker_factory: Callable[[], PrecipitationTracker] = PrecipitationTracker,
    ) -> None:
        self._repository = repository
        self._broadcaster = broadcaster
        self._aggregator = SnapshotAggregator(window=timedelta(seconds=window_seconds))
        self._precipitation_tracker_factory = precipitation_tracker_factory
        self._precipitation_trackers: dict[str, PrecipitationTracker] = {}

    def accept(self, event: MeasurementEvent) -> None:
        snapshot = self._aggregator.accept(
            event.device_id,
            event.measurement,
            event.value,
            event.received_at,
        )
        
        if snapshot is not None:
            self._repository.save(snapshot)
            if self._broadcaster is not None:
                tracker = self._precipitation_trackers.setdefault(
                    snapshot.device_id,
                    self._precipitation_tracker_factory(),
                )
                self._broadcaster.publish(tracker.update(snapshot))

    def expire(self, now) -> list[str]:
        return self._aggregator.expire(now)