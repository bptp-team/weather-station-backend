"""Version 1 of the public API. Newer versions live alongside it in app/api/v2, etc."""

from fastapi import APIRouter

from app.api.v1.routes.readings import router as readings_router


router = APIRouter()
router.include_router(readings_router)
