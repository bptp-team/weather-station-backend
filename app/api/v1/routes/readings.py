import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.formatters.weather import snapshot_to_api_payload
from app.services.broadcaster import SnapshotSubscription, SubscriptionClosed
from app.models.weather import WeatherSnapshot


SUBSCRIPTION_POLL_INTERVAL_SECONDS = 15.0


router = APIRouter(prefix="/readings", tags=["readings"])


async def _stream_snapshots(
    subscription: SnapshotSubscription,
) -> AsyncIterator[str]:
    try:
        while True:
            snapshot = await asyncio.to_thread(
                subscription.get,
                SUBSCRIPTION_POLL_INTERVAL_SECONDS,
            )
            if snapshot is None:
                yield ": keep-alive\n\n"
                continue

            event_data = json.dumps(
                _snapshot_to_event_payload(snapshot),
                default=_serialize_value,
            )
            yield f"data: {event_data}\n\n"
    except SubscriptionClosed:
        return
    finally:
        subscription.close()


def _snapshot_to_event_payload(snapshot: WeatherSnapshot) -> dict[str, object]:
    return snapshot_to_api_payload(snapshot)


def _serialize_value(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported SSE value: {type(value).__name__}")


@router.get(
    "/{station_id}/stream",
    summary="Stream weather snapshots as server-sent events",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "An open server-sent events stream. Each `data:` frame carries one "
                "complete snapshot; comment frames (`: keep-alive`) are sent every "
                f"{SUBSCRIPTION_POLL_INTERVAL_SECONDS:.0f} seconds while no snapshot "
                "is available, so proxies keep the connection open."
            ),
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": (
                        "data: {"
                        '"device_id": "station-01", '
                        '"air_temperature": 23.45, '
                        '"air_pressure": 1.0, '
                        '"air_humidity": 45.0, '
                        '"air_quality": 4, '
                        '"daylight": 2748, '
                        '"precipitation_interval": 0.0, '
                        '"received_at": "2026-09-06T00:00:00+00:00"'
                        "}\n\n"
                    ),
                }
            },
        }
    },
)
async def stream_readings(station_id: str, request: Request) -> StreamingResponse:
    """Stream snapshots for one station to the caller as they are aggregated.

    Every value is forwarded with formatting applied at the API boundary:
    `air_pressure` is converted from pascal to atmospheres, and raw water level ADC
    is converted to interval precipitation with drainage compensation.

    - `device_id`: identifier of the station that produced the snapshot, taken
      from the MQTT topic `weather/<device-id>/<measurement>`.
    - `air_temperature`: air temperature in degrees Celsius.
    - `air_pressure`: atmospheric pressure in **standard atmospheres (atm)**.
      The firmware publishes pascal and InfluxDB stores pascal; the conversion
      (1 atm = 101325 Pa) happens only here, at the API boundary.
    - `air_humidity`: relative air humidity as a percentage.
    - `air_quality`: air quality reading as a raw integer. The backend neither
      scales nor classifies it.
    - `daylight`: the voltage produced by the LDR module.
    - `precipitation_interval`: estimated precipitation depth in mm during the interval.
    - `received_at`: ISO 8601 UTC timestamp of when the backend received the
      measurement that completed the snapshot. The backend clock is used
      because the firmware does not publish a timestamp.
    """
    broadcaster = request.app.state.snapshot_broadcaster
    subscription = broadcaster.subscribe(station_id)
    return StreamingResponse(
        _stream_snapshots(subscription),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )