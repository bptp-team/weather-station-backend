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

Each `data:` frame carries **one snapshot** as **JSON**. A new connection first
receives the latest snapshot for its station. A `: keep-alive` comment frame is sent every **15
seconds of silence** so **proxies keep the connection open**:

```text
data: {"device_id": "station-01", "air_temperature": 23.45, "air_pressure": 1.0, "air_humidity": 45.0, "air_quality": 4, "daylight": 2748, "precipitation_interval": 0.0, "received_at": "2026-09-06T00:00:00+00:00"}
```

The floating-point measurements (`air_temperature`, `air_pressure`, `air_humidity`,
`precipitation_interval`) are returned rounded to
**two decimal places**. Integer measurements (`air_quality`, `daylight`) are
forwarded as integers. `air_pressure` is converted from **pascal** to
**atmospheres** before rounding.

| Field | Unit | Notes |
| ----- | ---- | ----- |
| `device_id` | — | **Station identifier**, taken from the **MQTT topic** |
| `air_temperature` | °C | |
| `air_pressure` | **atm** | Converted from the **pascal** published over **MQTT** |
| `air_humidity` | % | **Relative humidity** |
| `air_quality` | raw integer | **Neither scaled nor classified** by the backend |
| `daylight` | raw integer | **Voltage** produced by the **LDR module** |
| `precipitation_interval` | mm | Estimated **rainfall in the interval** between readings with **drainage compensation** |
| `received_at` | ISO 8601 UTC | **Backend clock**; the firmware sends **no timestamp** |

The **pressure conversion** (`1 atm = 101325 Pa`), **precipitation conversion** (ADC $\to$ Volume $\to$ mm),
and response rounding happen **only at the API boundary** — the **ingestion pipeline** and **InfluxDB**
keep storing the original values in **pascal** and raw **water_level ADC**, so the **stored history
keeps full precision in a single unit**.

### Rain Gauge (Pluviometer) Conversion & Drainage Compensation

The weather station adapts a resistive PCB water level probe mounted vertically inside a container with a collection funnel and drainage orifice:
- **Funnel Area ($A_f$):** For diameter $D_f = 7.5\text{ cm}$, area $A_f = \pi \times (3.75\text{ cm})^2 \approx 44.18\text{ cm}^2$.
- **Volume to Rain Equivalent:** $1\text{ mm of rain} \equiv 4.42\text{ mL}$ ($4.42\text{ mL/mm}$).
- **ADC to Volume ($V$):**
  $$V(\text{ADC}) = \begin{cases} 0.0\text{ mL}, & \text{ADC} \le 50 \\ \frac{\text{ADC} - 50}{10.0}\text{ mL}, & \text{ADC} > 50 \end{cases}$$
- **Drainage Mass Balance:**
  - $V_{\text{drained}} = \min(V_{\text{prev}}, Q_{\text{drain}} \times \Delta t)$, where $Q_{\text{drain}}$ defaults to $1.25\text{ mL/s}$.
  - $V_{\text{rain}} = \max(0.0, (V_{\text{curr}} - V_{\text{prev}}) + V_{\text{drained}})$.
  - $P_{\text{interval}} = \frac{V_{\text{rain}}}{4.42}\text{ mm}$.
  - The first reading of a new UTC day establishes a new volume baseline.

## Historical readings

Historical weather snapshots can be retrieved over HTTP as a JSON list:

```text
GET /api/v1/readings/{station_id}?from=2026-09-01T00:00:00Z&to=2026-09-07T00:00:00Z
```

The `from` and `to` parameters are optional when requesting the current UTC day.
If one is provided, both must be provided. The interval is half-open (`[from, to)`)
and cannot exceed 15 days; exactly 15 days is accepted. An empty result returns
`200 []`.

Each historical object has the same public weather fields as a streaming event.
The raw `water_level` ADC reading is retained internally for calculating
`precipitation_interval`, but is not returned by this endpoint.

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

Run the backend in development mode with:

```text
make dev
```

For a production-like app, the current command is:

```text
make prod
```

This runs:

```text
uv run fastapi run app/main.py --host 0.0.0.0 --port $(WEATHER_BACKEND_PORT) --workers 1
```

## Docker

The `Dockerfile` installs the **locked dependencies** with **uv** and runs the
app with `fastapi run` on **Python 3.12**. The **final image** carries **only
the virtual environment and the `app/` package**: **no uv, no lockfile and no
development dependencies**.

### Build

```sh
docker build -t weather-station-backend .
```

The build uses `uv sync --locked`, which **fails if `uv.lock` is out of date**
instead of resolving the dependencies again. It is the same check `make sync`
performs.

### Run

**All configuration comes from the environment**, never from the image. The
`.env` file **stays on the host** and is read at **run time**:

```sh
docker run -d --name weather-station-backend --env-file .env -p 8000:8000 weather-station-backend
```

Without `--env-file`, the defaults in `app/core/settings.py` point at
`127.0.0.1`, which inside a container means **the container itself**. Set at
least `WEATHER_MQTT_HOST`, `WEATHER_INFLUX_URL` and `WEATHER_ALLOWED_ORIGINS`.

In **production**, bind to `127.0.0.1` so the container is **reachable only by
the reverse proxy** on the same machine:

```sh
docker run -d --name weather-station-backend --restart unless-stopped --env-file .env -p 127.0.0.1:8000:8000 weather-station-backend
```

### Verify

```sh
docker exec weather-station-backend id             # uid=10001(app)
curl http://localhost:8000/openapi.json             # API answering
curl -N http://localhost:8000/api/v1/readings/station-01/stream
docker image ls weather-station-backend             # total image size
docker history weather-station-backend              # size of each layer
```

### Image details

- The app runs as a **non-root user** with **fixed UID** `10001` and listens
  on port `8000`.
- The **virtual environment** and the **source files** belong to `root`, so the
  process can **read them but cannot change them**.
- `--workers 1` is **explicit**: the **MQTT subscription** and the **InfluxDB
  writes** live **inside the application process**, so **every extra worker
  would store each reading again**.
- The **dependencies' bytecode** is **compiled during the build**
  (`UV_COMPILE_BYTECODE=1`), so start up does not depend on writing `.pyc`
  files, which **a non-root user cannot do**.
- `.dockerignore` **blocks every file by default**. When the build starts
  needing a **new file**, **add it both** to `.dockerignore` **and** to a
  `COPY` instruction in the `Dockerfile`.
