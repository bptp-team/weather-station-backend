from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEATHER_", env_file=".env", extra="ignore")

    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_topic: str = "weather/+/+"
    mqtt_client_id: str = "weather-station-backend"

    influx_url: str = "http://127.0.0.1:8181"
    influx_database: str = "weather-station-db"
    influx_measurement: str = "weather_reading"
    snapshot_window_seconds: int = 30