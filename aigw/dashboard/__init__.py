from fastapi import APIRouter

from aigw.dashboard.routes_auth import router as auth_router
from aigw.dashboard.routes_users import router as users_router
from aigw.dashboard.routes_keys import router as keys_router
from aigw.dashboard.routes_overview import router as overview_router
from aigw.dashboard.routes_config import router as config_router
from aigw.dashboard.routes_analytics import router as analytics_router
from aigw.dashboard.routes_gateway_keys import router as gateway_keys_router
from aigw.dashboard.routes_logs import router as logs_router
from aigw.dashboard.routes_service_accounts import router as service_accounts_router
from aigw.dashboard.routes_nine_router import router as nine_router_router

dashboard_router = APIRouter(prefix="/api", tags=["dashboard"])
dashboard_router.include_router(auth_router)
dashboard_router.include_router(users_router)
dashboard_router.include_router(keys_router)
dashboard_router.include_router(overview_router)
dashboard_router.include_router(config_router)
dashboard_router.include_router(analytics_router)
dashboard_router.include_router(gateway_keys_router)
dashboard_router.include_router(logs_router)
dashboard_router.include_router(service_accounts_router)
dashboard_router.include_router(nine_router_router)
