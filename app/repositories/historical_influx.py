import json
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

import pyarrow as pa
from influxdb_client_3 import InfluxDBClient3

from app.models.weather import WeatherSnapshot


class QueryableInfluxClient(Protocol):
    def query(self, query: str, **kwargs: object) -> Any:
        """Execute a SQL query against InfluxDB."""


class HistoricalDayCache(Protocol):
    def get(
        self,
        station_id: str,
        utc_date: date,
        *,
        namespace: str = "default",
    ) -> list[dict[str, object]] | None:
        """Return cached raw rows for a complete UTC day, if present."""

    def put(
        self,
        station_id: str,
        utc_date: date,
        rows: list[dict[str, object]],
        *,
        namespace: str = "default",
    ) -> None:
        """Persist raw rows for a complete UTC day."""

    def prune_before(self, cutoff: date) -> None:
        """Remove cached days older than the retention cutoff."""


class HistoricalInfluxRepository:
    def __init__(
        self,
        client: InfluxDBClient3 | QueryableInfluxClient,
        *,
        database: str,
        measurement_name: str,
        cache: HistoricalDayCache | None = None,
        now: Callable[[], datetime] | None = None,
        retention_days: int = 15,
    ) -> None:
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        self._client = client
        self._database = database
        self._measurement_name = measurement_name
        self._cache = cache
        self._cache_namespace = json.dumps(
            [database, measurement_name],
            separators=(",", ":"),
        )
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._retention_days = retention_days

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
    water_level,
    latitude,
    longitude
FROM {self._quote_identifier(self._measurement_name)}
WHERE device_id = $station_id
  AND time >= $start
  AND time < $end
  AND air_temperature IS NOT NULL
  AND air_pressure IS NOT NULL
  AND air_humidity IS NOT NULL
  AND air_quality IS NOT NULL
  AND daylight IS NOT NULL
  AND water_level IS NOT NULL
ORDER BY time
'''
        requested_start = start.astimezone(timezone.utc)
        requested_end = end.astimezone(timezone.utc)
        cursor = requested_start.replace(hour=0, minute=0, second=0, microsecond=0)
        snapshots: list[WeatherSnapshot] = []
        now = self._normalize_received_at(self._now())
        retention_cutoff = now - timedelta(days=self._retention_days)
        current_day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if self._cache is not None:
            self._cache.prune_before(retention_cutoff.date())

        while cursor < requested_end:
            query_end = cursor + timedelta(days=1)
            is_completed_day = query_end <= current_day_start
            is_cacheable_day = (
                is_completed_day and cursor.date() >= retention_cutoff.date()
            )
            cached_rows = (
                self._cache.get(
                    station_id,
                    cursor.date(),
                    namespace=self._cache_namespace,
                )
                if self._cache is not None and is_cacheable_day
                else None
            )
            came_from_cache = cached_rows is not None
            rows = cached_rows
            if rows is None:
                result = self._client.query(
                    query,
                    language="sql",
                    mode="all",
                    database=self._database,
                    query_parameters={
                        "station_id": station_id,
                        "start": cursor.isoformat(),
                        "end": query_end.isoformat(),
                    },
                )
                rows = self._result_rows(result)
                if self._cache is not None and is_cacheable_day:
                    self._cache.put(
                        station_id,
                        cursor.date(),
                        rows,
                        namespace=self._cache_namespace,
                    )

            for row in rows:
                received_at = self._normalize_received_at(row["time"])
                if (
                    requested_start <= received_at < requested_end
                    and (not came_from_cache or retention_cutoff <= received_at)
                ):
                    snapshots.append(self._row_to_snapshot(row))
            cursor = query_end

        return snapshots

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
        received_at = HistoricalInfluxRepository._normalize_received_at(row["time"])
        latitude = row.get("latitude")
        longitude = row.get("longitude")
        if latitude is None or longitude is None:
            raise ValueError(
                "Historical reading coordinates must be backfilled before serving history"
            )
        return WeatherSnapshot(
            device_id=str(row["device_id"]),
            air_temperature=float(row["air_temperature"]),
            air_pressure=float(row["air_pressure"]),
            air_humidity=float(row["air_humidity"]),
            air_quality=int(row["air_quality"]),
            daylight=int(row["daylight"]),
            water_level=int(row["water_level"]),
            received_at=received_at,
            latitude=float(latitude),
            longitude=float(longitude),
        )

    @staticmethod
    def _normalize_received_at(received_at: datetime | str) -> datetime:
        if isinstance(received_at, str):
            received_at = datetime.fromisoformat(received_at)
        if received_at.tzinfo is None or received_at.utcoffset() is None:
            return received_at.replace(tzinfo=timezone.utc)
        return received_at.astimezone(timezone.utc)
