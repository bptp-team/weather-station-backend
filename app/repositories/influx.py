import logging
from typing import Protocol

from influxdb_client_3 import InfluxDBClient3, Point

from app.models.weather import InfluxPoint, WeatherSnapshot

logger = logging.getLogger(__name__)


class SnapshotRepository(Protocol):
    def save(self, snapshot: WeatherSnapshot) -> None:
        """Persist one complete station snapshot."""


def snapshot_to_point(
    snapshot: WeatherSnapshot,
    *,
    measurement_name: str,
) -> InfluxPoint:
    return InfluxPoint(
        measurement=measurement_name,
        tags={"device_id": snapshot.device_id},
        fields={
            "airTemperature": snapshot.air_temperature,
            "airPressure": snapshot.air_pressure,
            "airHumidity": snapshot.air_humidity,
            "daylight": snapshot.daylight,
            "waterLevel": snapshot.water_level,
            "airQuality": snapshot.air_quality,
        },
        time=snapshot.received_at,
    )


class InfluxRepository:
    def __init__(
        self,
        client: InfluxDBClient3,
        *,
        database: str,
        measurement_name: str,
    ) -> None:
        self._client = client
        self._database = database
        self._measurement_name = measurement_name

    def save(self, snapshot: WeatherSnapshot) -> None:
        point = snapshot_to_point(snapshot, measurement_name=self._measurement_name)
        influx_point = Point(point.measurement).tag("device_id", point.tags["device_id"])

        for field, value in point.fields.items():
            influx_point = influx_point.field(field, value)

        self._client.write(record=influx_point, database=self._database)
        logger.info(
            "Saved weather snapshot to InfluxDB: database=%s measurement=%s device_id=%s timestamp=%s",
            self._database,
            point.measurement,
            snapshot.device_id,
            snapshot.received_at.isoformat(),
        )

    def close(self) -> None:
        self._client.close()