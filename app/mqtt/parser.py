from datetime import datetime, timezone

from app.models.weather import MeasurementEvent, MeasurementValue


_FLOAT_MEASUREMENTS = {"airTemperature", "airPressure", "airHumidity"}
_INT_MEASUREMENTS = {"daylight", "waterLevel", "airQuality"}
_MEASUREMENTS = _FLOAT_MEASUREMENTS | _INT_MEASUREMENTS


def parse_message(
    topic: str,
    payload: bytes,
    *,
    received_at: datetime | None = None,
) -> MeasurementEvent:
    topic_segments = topic.split("/")

    has_valid_topic_structure = (
        len(topic_segments) == 3
        and topic_segments[0] == "weather"
        and bool(topic_segments[1])
    )

    if not has_valid_topic_structure:
        raise ValueError(f"Invalid MQTT topic: {topic!r}")

    device_id, measurement = topic_segments[1], topic_segments[2]
    
    if not measurement or measurement not in _MEASUREMENTS:
        raise ValueError(f"Unknown MQTT measurement: {measurement!r}")

    text = payload.decode("utf-8").strip()
    if not text:
        raise ValueError("MQTT payload cannot be empty")

    value: MeasurementValue
    try:
        if measurement in _FLOAT_MEASUREMENTS:
            value = float(text)
        else:
            value = int(text)
    except UnicodeDecodeError as error:
        raise ValueError("MQTT payload must be UTF-8") from error
    except ValueError as error:
        raise ValueError(f"Invalid value for {measurement}: {text!r}") from error

    return MeasurementEvent(
        device_id=device_id,
        measurement=measurement,
        value=value,
        received_at=received_at or datetime.now(timezone.utc),
    )