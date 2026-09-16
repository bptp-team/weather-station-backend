from app.models.weather import WeatherSnapshot
from app.utils.precipitation import PrecipitationTracker
from app.utils.units import pascal_to_atm


def snapshot_to_api_payload(
    snapshot: WeatherSnapshot,
) -> dict[str, object]:
    """Format one internal snapshot for public API transport."""
    return {
        "device_id": snapshot.device_id,
        "air_temperature": round(snapshot.air_temperature, 2),
        "air_pressure": round(pascal_to_atm(snapshot.air_pressure), 2),
        "air_humidity": round(snapshot.air_humidity, 2),
        "air_quality": snapshot.air_quality,
        "daylight": snapshot.daylight,
        "precipitation_interval": round(snapshot.precipitation_interval, 2),
        "received_at": snapshot.received_at.isoformat(),
    }


def format_snapshots_history(
    snapshots: list[WeatherSnapshot],
    tracker: PrecipitationTracker | None = None,
) -> list[dict[str, object]]:
    """Format an ordered sequence of historical snapshots with rain tracking."""
    if not snapshots:
        return []

    if tracker is None:
        tracker = PrecipitationTracker()
    else:
        tracker.reset()

    formatted: list[dict[str, object]] = []
    for snapshot in snapshots:
        formatted.append(snapshot_to_api_payload(tracker.update(snapshot)))
    return formatted
