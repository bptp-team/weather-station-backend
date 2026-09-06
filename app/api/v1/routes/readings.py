import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.broadcaster import SnapshotSubscription, SubscriptionClosed


SUBSCRIPTION_POLL_INTERVAL_SECONDS = 15.0


router = APIRouter(prefix="/readings", tags=["readings"])


async def _stream_snapshots(subscription: SnapshotSubscription) -> AsyncIterator[str]:
    try:
        while True:
            snapshot = await asyncio.to_thread(
                subscription.get,
                SUBSCRIPTION_POLL_INTERVAL_SECONDS,
            )
            if snapshot is None:
                yield ": keep-alive\n\n"
                continue

            event_data = json.dumps(asdict(snapshot), default=_serialize_value)
            yield f"data: {event_data}\n\n"
    except SubscriptionClosed:
        return
    finally:
        subscription.close()


def _serialize_value(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported SSE value: {type(value).__name__}")


@router.get("/stream")
async def stream_readings(request: Request) -> StreamingResponse:
    broadcaster = request.app.state.snapshot_broadcaster
    subscription = broadcaster.subscribe()
    return StreamingResponse(
        _stream_snapshots(subscription),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )