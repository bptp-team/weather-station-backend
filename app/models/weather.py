from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias


MeasurementValue: TypeAlias = float | int | str


@dataclass(frozen=True)
class MeasurementEvent:
    device_id: str
    measurement: str
    value: MeasurementValue
    received_at: datetime


@dataclass(frozen=True)
class WeatherSnapshot:
    device_id: str
    air_temperature: float
    air_pressure: float
    air_humidity: float
    air_quality: int
    daylight: str
    water_level: int
    received_at: datetime


@dataclass(frozen=True)
class InfluxPoint:
    measurement: str
    tags: dict[str, str]
    fields: dict[str, MeasurementValue]
    time: datetime