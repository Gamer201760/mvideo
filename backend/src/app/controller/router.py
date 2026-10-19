from fastapi import APIRouter

from app.controller.health.router import router as health_router
from app.controller.stand.batch_router import router as batch_router
from app.controller.stand.history_router import router as history_router
from app.controller.stand.review_router import router as review_router
from app.controller.stand.router import router as stand_router

api_router_v1 = APIRouter(prefix="/api/v1")
api_router_v1.include_router(health_router)
api_router_v1.include_router(stand_router)
api_router_v1.include_router(batch_router)
api_router_v1.include_router(review_router)
api_router_v1.include_router(history_router)
