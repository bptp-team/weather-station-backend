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

The backend subscribes to `weather/+/+`, matching the **firmware topics**:

```text
weather/<device-id>/airTemperature
weather/<device-id>/airPressure
weather/<device-id>/airHumidity
weather/<device-id>/daylight
weather/<device-id>/waterLevel
weather/<device-id>/airQuality
```

It validates the **plain-text payloads**, collects **all six measurements** per
device within **30 seconds**, and writes **one complete snapshot** to
**InfluxDB**. **Incomplete snapshots are discarded.** The **backend timestamp**
is used because the **firmware does not publish one**.

## Streaming

**Complete snapshots** are also pushed to connected clients as **server-sent
events**:

```text
GET /api/v1/readings/{station_id}/stream
```

Each `data:` frame carries **one snapshot** as **JSON**, and a `: keep-alive`
comment frame is sent every **15 seconds of silence** so **proxies keep the
connection open**:

```text
data: {"device_id": "station-01", "air_temperature": 23.45, "air_pressure": 1.0, "air_humidity": 45.0, "air_quality": 4, "daylight": 2748, "water_level": 12, "received_at": "2026-09-06T00:00:00+00:00"}
```

The three floating-point measurements are returned rounded to **two decimal
places**. Integer measurements are forwarded as integers. `air_pressure` is
also converted from **pascal** to **atmospheres** before rounding.

| Field | Unit | Notes |
| ----- | ---- | ----- |
| `device_id` | — | **Station identifier**, taken from the **MQTT topic** |
| `air_temperature` | °C | |
| `air_pressure` | **atm** | Converted from the **pascal** published over **MQTT** |
| `air_humidity` | % | **Relative humidity** |
| `air_quality` | raw integer | **Neither scaled nor classified** by the backend |
| `daylight` | raw integer | **Voltage** produced by the **LDR module** |
| `water_level` | raw integer | **Voltage** produced by the **water level sensor** |
| `received_at` | ISO 8601 UTC | **Backend clock**; the firmware sends **no timestamp** |

The **pressure conversion** (`1 atm = 101325 Pa`) and response rounding happen
**only at the API boundary** — the **ingestion pipeline** and **InfluxDB** keep
storing the original values in **pascal**, so the **stored history keeps full
precision in a single unit**.

## Historical readings

Complete snapshots can be retrieved over HTTP as a JSON list:

```text
GET /api/v1/readings/{station_id}?from=2026-09-01T00:00:00Z&to=2026-09-07T00:00:00Z
```

The `from` and `to` parameters are optional when requesting the current UTC day.
If one is provided, both must be provided. The interval is half-open (`[from, to)`)
and cannot exceed 15 days; exactly 15 days is accepted. An empty result returns
`200 []`.

The JSON object for each historical reading has exactly the same fields and units
as each streaming `data:` event. In particular, `air_pressure` is returned in
**atmospheres** and `received_at` is an ISO 8601 string.

The interactive **Swagger documentation** is served at `/docs` once the backend
is running.

**Local defaults** target the **platform repository's services**:

```text
WEATHER_MQTT_HOST=127.0.0.1
WEATHER_MQTT_PORT=1883
WEATHER_INFLUX_URL=http://127.0.0.1:8181
WEATHER_INFLUX_DATABASE=weather-station-db
WEATHER_INFLUX_MEASUREMENT=weather_reading
WEATHER_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Override settings with **environment variables** prefixed by `WEATHER_`. Set
`WEATHER_ALLOWED_ORIGINS` to the **browser client origins** allowed to access
the **API**. Separate multiple origins with **commas and no spaces**, for
example `http://localhost:5173,http://192.168.1.10:5173`. The local
**InfluxDB 3** development connection **does not use authentication**.

Run the backend with:

```text
make dev
```
