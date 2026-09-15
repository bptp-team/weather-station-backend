from app.models.weather import WeatherSnapshot
from app.utils.units import pascal_to_atm


def snapshot_to_api_payload(snapshot: WeatherSnapshot) -> dict[str, object]:
    """Format one internal snapshot for every public API transport."""
    return {
        "device_id": snapshot.device_id,
        "air_temperature": round(snapshot.air_temperature, 2),
        "air_pressure": round(pascal_to_atm(snapshot.air_pressure), 2),
        "air_humidity": round(snapshot.air_humidity, 2),
        "air_quality": snapshot.air_quality,
        "daylight": snapshot.daylight,
        "water_level": snapshot.water_level,
        "received_at": snapshot.received_at.isoformat(),
    }
