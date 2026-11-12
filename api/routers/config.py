"""Public client configuration (browser-safe keys)."""

from fastapi import APIRouter

from api.schemas import ClientConfigResponse
from api.settings import settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/client", response_model=ClientConfigResponse)
async def client_config() -> ClientConfigResponse:
    return ClientConfigResponse(
        google_maps_api_key=settings.google_maps_api_key,
    )
