from datetime import datetime
from typing import Any, Protocol

from influxdb_client_3 import InfluxDBClient3

from app.models.weather import WeatherSnapshot


class QueryableInfluxClient(Protocol):
    def query(self, query: str, **kwargs: object) -> Any:
        """Execute a SQL query against InfluxDB."""


class HistoricalInfluxRepository:
    def __init__(
        self,
        client: InfluxDBClient3 | QueryableInfluxClient,
        *,
        database: str,
        measurement_name: str,
    ) -> None:
        self._client = client
        self._database = database
        self._measurement_name = measurement_name

    def read(self, station_id: str, start: datetime, end: datetime) -> list[WeatherSnapshot]:
        query = f'''
SELECT
    time,
    device_id,
    airTemperature,
    airPressure,
    airHumidity,
    airQuality,
    daylight,
    waterLevel
FROM {self._quote_identifier(self._measurement_name)}
WHERE device_id = $station_id
  AND time >= $start
  AND time < $end
ORDER BY time
'''
        result = self._client.query(
            query,
            language="sql",
            mode="all",
            database=self._database,
            query_parameters={
                "station_id": station_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        return [self._row_to_snapshot(row) for row in self._result_rows(result)]

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _result_rows(result: Any) -> list[dict[str, Any]]:
        if hasattr(result, "to_pylist"):
            return result.to_pylist()
        if hasattr(result, "to_dict"):
            return result.to_dict(orient="records")
        return list(result)

    @staticmethod
    def _row_to_snapshot(row: dict[str, Any]) -> WeatherSnapshot:
        received_at = row["time"]
        if isinstance(received_at, str):
            received_at = datetime.fromisoformat(received_at)
        return WeatherSnapshot(
            device_id=str(row["device_id"]),
            air_temperature=float(row["airTemperature"]),
            air_pressure=float(row["airPressure"]),
            air_humidity=float(row["airHumidity"]),
            air_quality=int(row["airQuality"]),
            daylight=int(row["daylight"]),
            water_level=int(row["waterLevel"]),
            received_at=received_at,
        )
