from app.models.weather import WeatherSnapshot
from app.utils.units import pascal_to_atm


def snapshot_to_api_payload(snapshot: WeatherSnapshot) -> dict[str, object]:
    """Format one internal snapshot for every public API transport."""
    return {
        "device_id": snapshot.device_id,
        "air_temperature": snapshot.air_temperature,
        "air_pressure": pascal_to_atm(snapshot.air_pressure),
        "air_humidity": snapshot.air_humidity,
        "air_quality": snapshot.air_quality,
        "daylight": snapshot.daylight,
        "water_level": snapshot.water_level,
        "received_at": snapshot.received_at.isoformat(),
    }
