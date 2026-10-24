import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

HISTORICAL_CACHE_SCHEMA_VERSION = 1


class SQLiteHistoricalDayCache:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._restrict_permissions(self._path.parent)

        with closing(sqlite3.connect(self._path, timeout=10)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS historical_days (
                        namespace TEXT NOT NULL,
                        station_id TEXT NOT NULL,
                        utc_date TEXT NOT NULL,
                        schema_version INTEGER NOT NULL,
                        rows_json TEXT NOT NULL,
                        PRIMARY KEY (namespace, station_id, utc_date, schema_version)
                    )
                    """
                )

        self._restrict_permissions(self._path)

    def get(
        self,
        station_id: str,
        utc_date: date,
        *,
        namespace: str = "default",
    ) -> list[dict[str, object]] | None:
        with closing(sqlite3.connect(self._path, timeout=10)) as connection:
            result = connection.execute(
                """
                SELECT rows_json
                FROM historical_days
                WHERE namespace = ? AND station_id = ? AND utc_date = ? AND schema_version = ?
                """,
                (
                    namespace,
                    station_id,
                    utc_date.isoformat(),
                    HISTORICAL_CACHE_SCHEMA_VERSION,
                ),
            ).fetchone()

        if result is None:
            return None

        rows = json.loads(result[0])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Invalid rows stored in historical day cache")
        return rows

    def put(
        self,
        station_id: str,
        utc_date: date,
        rows: list[dict[str, object]],
        *,
        namespace: str = "default",
    ) -> None:
        if not rows:
            return

        rows_json = json.dumps(rows, default=self._serialize_value, separators=(",", ":"))
        with closing(sqlite3.connect(self._path, timeout=10)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO historical_days (
                        namespace, station_id, utc_date, schema_version, rows_json
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (namespace, station_id, utc_date, schema_version)
                    DO UPDATE SET rows_json = excluded.rows_json
                    """,
                    (
                        namespace,
                        station_id,
                        utc_date.isoformat(),
                        HISTORICAL_CACHE_SCHEMA_VERSION,
                        rows_json,
                    ),
                )

    def prune_before(self, cutoff: date) -> None:
        with closing(sqlite3.connect(self._path, timeout=10)) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM historical_days WHERE utc_date < ?",
                    (cutoff.isoformat(),),
                )

    @staticmethod
    def _serialize_value(value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Unsupported historical cache value: {type(value).__name__}")

    @staticmethod
    def _restrict_permissions(path: Path) -> None:
        if os.name == "posix":
            path.chmod(0o700 if path.is_dir() else 0o600)
