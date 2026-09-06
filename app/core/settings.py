from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEATHER_", env_file=".env", extra="ignore")

    allowed_origins: str = ""
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_topic: str = "weather/+/+"
    mqtt_client_id: str = "weather-station-backend"

    influx_url: str = "http://127.0.0.1:8181"
    influx_database: str = "weather-station-db"
    influx_measurement: str = "weather_reading"
    snapshot_window_seconds: int = 30

    @field_validator("allowed_origins")
    @classmethod
    def reject_wildcard_origin(cls, value: str) -> str:
        if "*" in value.split(","):
            raise ValueError("Wildcard CORS origins are not allowed")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return self.allowed_origins.split(",") if self.allowed_origins else []