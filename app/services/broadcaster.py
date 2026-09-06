from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Lock

from app.models.weather import WeatherSnapshot


class SubscriptionClosed(Exception):
    pass


class SnapshotSubscription:
    def __init__(
        self,
        broadcaster: SnapshotBroadcaster,
        station_id: str,
        queue: Queue[WeatherSnapshot | None],
    ) -> None:
        self._broadcaster = broadcaster
        self.station_id = station_id
        self._queue = queue

    def get(self, timeout: float) -> WeatherSnapshot | None:
        try:
            snapshot = self._queue.get(timeout=timeout)
        except Empty:
            return None

        if snapshot is None:
            raise SubscriptionClosed
        return snapshot

    def close(self) -> None:
        self._broadcaster.unsubscribe(self)


class SnapshotBroadcaster:
    def __init__(self, *, queue_size: int = 10) -> None:
        self._queue_size = queue_size
        self._subscriptions: dict[SnapshotSubscription, Queue[WeatherSnapshot | None]] = {}
        self._lock = Lock()

    def subscribe(self, station_id: str) -> SnapshotSubscription:
        subscription = SnapshotSubscription(
            self,
            station_id,
            Queue(maxsize=self._queue_size),
        )
        with self._lock:
            self._subscriptions[subscription] = subscription._queue
        return subscription

    def unsubscribe(self, subscription: SnapshotSubscription) -> None:
        with self._lock:
            queue = self._subscriptions.pop(subscription, None)

        if queue is not None:
            self._signal_close(queue)

    def publish(self, snapshot: WeatherSnapshot) -> None:
        with self._lock:
            subscriptions = tuple(self._subscriptions.items())

        for subscription, queue in subscriptions:
            if subscription.station_id == snapshot.device_id:
                self._put_latest(queue, snapshot)

    def close(self) -> None:
        with self._lock:
            queues = tuple(self._subscriptions.values())
            self._subscriptions.clear()

        for queue in queues:
            self._signal_close(queue)

    @staticmethod
    def _put_latest(queue: Queue[WeatherSnapshot | None], snapshot: WeatherSnapshot) -> None:
        try:
            queue.put_nowait(snapshot)
        except Full:
            queue.get_nowait()
            queue.put_nowait(snapshot)

    @staticmethod
    def _signal_close(queue: Queue[WeatherSnapshot | None]) -> None:
        try:
            queue.put_nowait(None)
        except Full:
            queue.get_nowait()
            queue.put_nowait(None)