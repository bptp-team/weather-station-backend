from pydantic import BaseModel, ConfigDict


class HistoricalReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    air_temperature: float
    air_pressure: float
    air_humidity: float
    air_quality: int
    daylight: int
    precipitation_interval: float
    received_at: str
