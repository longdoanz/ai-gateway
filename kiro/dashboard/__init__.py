from fastapi import APIRouter

from kiro.dashboard.routes_auth import router as auth_router
from kiro.dashboard.routes_users import router as users_router
from kiro.dashboard.routes_keys import router as keys_router
from kiro.dashboard.routes_overview import router as overview_router
from kiro.dashboard.routes_config import router as config_router
from kiro.dashboard.routes_import import router as import_router
from kiro.dashboard.routes_analytics import router as analytics_router
from kiro.dashboard.routes_gateway_keys import router as gateway_keys_router
from kiro.dashboard.routes_system_keys import router as system_keys_router

dashboard_router = APIRouter(prefix="/api", tags=["dashboard"])
dashboard_router.include_router(auth_router)
dashboard_router.include_router(users_router)
dashboard_router.include_router(keys_router)
dashboard_router.include_router(overview_router)
dashboard_router.include_router(config_router)
dashboard_router.include_router(import_router)
dashboard_router.include_router(analytics_router)
dashboard_router.include_router(gateway_keys_router)
dashboard_router.include_router(system_keys_router)
