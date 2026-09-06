import json
import logging
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from influxdb_client_3 import InfluxDBClient3

from app.core.settings import Settings

logger = logging.getLogger(__name__)


def create_influx_client(settings: Settings) -> InfluxDBClient3:
    client = InfluxDBClient3(
        host=settings.influx_url,
        database=settings.influx_database,
        token="",
        write_use_v2_api=False,
    )
    client.default_header.pop("Authorization", None)
    return client


def ensure_database_exists(settings: Settings) -> None:
    request_url = f"{settings.influx_url.rstrip('/')}/api/v3/configure/database"
    request_body = json.dumps({"db": settings.influx_database}).encode("utf-8")
    request = Request(
        request_url,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=10):
            logger.info("Created InfluxDB database: database=%s", settings.influx_database)
    except HTTPError as error:
        if error.code == 409:
            logger.info("InfluxDB database already exists: database=%s", settings.influx_database)
        else:
            raise