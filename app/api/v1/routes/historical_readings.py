from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.formatters.weather import format_snapshots_history
from app.schemas.historical_reading import HistoricalReading
from app.services.historical_readings import (
    HistoricalReadingsService,
    InvalidReadingRange,
)


router = APIRouter(prefix="/readings", tags=["readings"])


@router.get(
    "/{station_id}",
    response_model=list[HistoricalReading],
    summary="Read historical weather snapshots",
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "The requested interval is invalid or exceeds 15 days."
        }
    },
)
def read_historical_readings(
    station_id: str,
    request: Request,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
) -> list[dict[str, object]]:
    if (from_ is None) != (to is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="from and to must be provided together",
        )

    service: HistoricalReadingsService = request.app.state.historical_readings_service
    try:
        snapshots = service.read(station_id, from_, to)
    except InvalidReadingRange as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    return format_snapshots_history(snapshots)
