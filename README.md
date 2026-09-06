### Weather Station Back-end

<p align="justify">
    <img
        src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/python/python-original.svg"
        width="50"
        height="50"
    />
    <img
        src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/fastapi/fastapi-original.svg"
        width="50"
        height="50"
    />
    <img
        src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/influxdb/influxdb-original.svg"
        width="50"
        height="50"
    />
    <img src="/docs/pydantic.svg" width="50" height="50" />
    <img src="/docs/uv.svg" width="50" height="50" />
    <img src="/docs/mosquitto.svg" width="50" height="50" />
</p>

## Ingestion

The backend subscribes to `weather/+/+`, matching the firmware topics:

```text
weather/<device-id>/airTemperature
weather/<device-id>/airPressure
weather/<device-id>/airHumidity
weather/<device-id>/daylight
weather/<device-id>/waterLevel
weather/<device-id>/airQuality
```

It validates the plain-text payloads, collects all six measurements per device
within 30 seconds, and writes one complete snapshot to InfluxDB. Incomplete
snapshots are discarded. The backend timestamp is used because the firmware
does not publish one.

## Streaming

Complete snapshots are also pushed to connected clients as server-sent events:

```text
GET /api/v1/readings/stream
```

Each `data:` frame carries one snapshot as JSON, and a `: keep-alive` comment
frame is sent every 15 seconds of silence so proxies keep the connection open:

```text
data: {"device_id": "station-01", "air_temperature": 23.45, "air_pressure": 1.0, "air_humidity": 45.0, "air_quality": 4, "daylight": 2748, "water_level": 12, "received_at": "2026-09-06T00:00:00+00:00"}
```

Every value is forwarded exactly as the firmware published it, with one
exception: `air_pressure`, which is converted from pascal to atmospheres.

| Field | Unit | Notes |
| ----- | ---- | ----- |
| `device_id` | — | Station identifier, taken from the MQTT topic |
| `air_temperature` | °C | |
| `air_pressure` | **atm** | Converted from the pascal published over MQTT |
| `air_humidity` | % | Relative humidity |
| `air_quality` | raw integer | Neither scaled nor classified by the backend |
| `daylight` | raw integer | Voltage produced by the LDR module |
| `water_level` | raw integer | Voltage produced by the water level sensor |
| `received_at` | ISO 8601 UTC | Backend clock; the firmware sends no timestamp |

The pressure conversion (1 atm = 101325 Pa) happens only at the API boundary —
the ingestion pipeline and InfluxDB keep storing pascal, so the stored history
stays in a single unit.

The interactive Swagger documentation is served at `/docs` once the backend is
running.

Local defaults target the platform repository's services:

```text
WEATHER_MQTT_HOST=127.0.0.1
WEATHER_MQTT_PORT=1883
WEATHER_INFLUX_URL=http://127.0.0.1:8181
WEATHER_INFLUX_DATABASE=weather-station-db
WEATHER_INFLUX_MEASUREMENT=weather_reading
WEATHER_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Override settings with environment variables prefixed by `WEATHER_`. Set
`WEATHER_ALLOWED_ORIGINS` to the browser client origins allowed to access the
API. Separate multiple origins with commas and no spaces, for example
`http://localhost:5173,http://192.168.1.10:5173`. The local InfluxDB 3
development connection does not use authentication.

Run the backend with:

```text
make dev
```
