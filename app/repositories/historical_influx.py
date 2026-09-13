from datetime import datetime
from typing import Any, Protocol

import pyarrow as pa
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
    air_temperature,
    air_pressure,
    air_humidity,
    air_quality,
    daylight,
    water_level
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
        if isinstance(result, pa.Table):
            return HistoricalInfluxRepository._normalize_arrow_timestamps(result).to_pylist()
        if hasattr(result, "to_pylist"):
            return result.to_pylist()
        if hasattr(result, "to_dict"):
            return result.to_dict(orient="records")
        return list(result)

    @staticmethod
    def _normalize_arrow_timestamps(result: pa.Table) -> pa.Table:
        original_schema = result.schema
        normalized_schema = pa.schema(
            [
            field.with_type(pa.timestamp("us", tz=field.type.tz))
            if pa.types.is_timestamp(field.type) and field.type.unit != "us"
            else field
                for field in original_schema
            ],
            metadata=original_schema.metadata,
        )
        if normalized_schema == original_schema:
            return result
        return result.cast(normalized_schema, safe=False)

    @staticmethod
    def _row_to_snapshot(row: dict[str, Any]) -> WeatherSnapshot:
        received_at = row["time"]
        if isinstance(received_at, str):
            received_at = datetime.fromisoformat(received_at)
        return WeatherSnapshot(
            device_id=str(row["device_id"]),
            air_temperature=float(row["air_temperature"]),
            air_pressure=float(row["air_pressure"]),
            air_humidity=float(row["air_humidity"]),
            air_quality=int(row["air_quality"]),
            daylight=int(row["daylight"]),
            water_level=int(row["water_level"]),
            received_at=received_at,
        )
