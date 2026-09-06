from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models.weather import MeasurementValue, WeatherSnapshot


_REQUIRED_MEASUREMENTS = {
    "airTemperature",
    "airPressure",
    "airHumidity",
    "airQuality",
    "daylight",
    "waterLevel",
}


@dataclass
class _PendingSnapshot:
    values: dict[str, MeasurementValue]
    updated_at: datetime


class SnapshotAggregator:
    def __init__(self, *, window: timedelta) -> None:
        self._window = window
        self._pending: dict[str, _PendingSnapshot] = {}

    def accept(
        self,
        device_id: str,
        measurement: str,
        value: MeasurementValue,
        received_at: datetime,
    ) -> WeatherSnapshot | None:
        pending = self._pending.setdefault(
            device_id,
            _PendingSnapshot(values={}, updated_at=received_at),
        )
        pending.values[measurement] = value
        pending.updated_at = received_at

        received_measurements = pending.values.keys()
        has_all_required_measurements = _REQUIRED_MEASUREMENTS <= received_measurements

        if has_all_required_measurements:
            snapshot = WeatherSnapshot(
                device_id=device_id,
                air_temperature=float(pending.values["airTemperature"]),
                air_pressure=float(pending.values["airPressure"]),
                air_humidity=float(pending.values["airHumidity"]),
                air_quality=int(pending.values["airQuality"]),
                daylight=str(pending.values["daylight"]),
                water_level=int(pending.values["waterLevel"]),
                received_at=received_at,
            )
            del self._pending[device_id]
            return snapshot

        return None

    def expire(self, now: datetime) -> list[str]:
        expired = [
            device_id
            for device_id, pending in self._pending.items()
            if self._has_expired(pending, now)
        ]

        for device_id in expired:
            del self._pending[device_id]
            
        return expired

    def _has_expired(self, pending: _PendingSnapshot, current_time: datetime) -> bool:
        elapsed_time = current_time - pending.updated_at
        return elapsed_time >= self._window