from fastapi import APIRouter

from app.controller.health.router import router as health_router
from app.controller.stand.router import router as stand_router
from app.controller.text.router import router as text_router

api_router_v1 = APIRouter(prefix="/api/v1")
api_router_v1.include_router(health_router)
api_router_v1.include_router(stand_router)
api_router_v1.include_router(text_router)
