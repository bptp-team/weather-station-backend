from influxdb_client_3 import InfluxDBClient3

from app.core.settings import Settings


def create_influx_client(settings: Settings) -> InfluxDBClient3:
    token = settings.influx_token.get_secret_value()
    client = InfluxDBClient3(
        host=settings.influx_url,
        database=settings.influx_database,
        token=token,
        write_use_v2_api=False,
    )
    if not token:
        client.default_header.pop("Authorization", None)
    return client
