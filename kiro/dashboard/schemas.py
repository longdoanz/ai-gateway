from datetime import datetime
from pydantic import BaseModel, Field


# --- Auth ---

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# --- User ---

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdate(BaseModel):
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6)
    role: str | None = Field(default=None, pattern="^(admin|user)$")


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserDetailResponse(UserResponse):
    api_keys: list["ApiKeyResponse"] = []


# --- ApiKey ---

class ApiKeyCreate(BaseModel):
    raw_key: str = Field(min_length=10)
    user_id: int | None = None  # admin can assign to a specific user


class ApiKeyResponse(BaseModel):
    id: int
    user_id: int
    kiro_user_id: str | None = None
    key_prefix: str
    key_suffix: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyToggle(BaseModel):
    is_active: bool


# --- KeyUsage ---

class KeyUsageResponse(BaseModel):
    month: str
    current_usage: int
    usage_limit: int
    last_synced_at: datetime | None = None
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


# --- Overview ---

class DailyUsage(BaseModel):
    date: str
    credits: int


class OverviewResponse(BaseModel):
    total_credits_used: int
    total_credits_limit: int
    total_users: int
    active_users: int
    active_keys: int
    daily_usage: list[DailyUsage]


# --- Config ---

class SystemConfigResponse(BaseModel):
    enable_model_override: bool = False
    enforced_global_model: str = "auto"
    enable_usage_sharing: bool = False


class SystemConfigUpdate(BaseModel):
    enable_model_override: bool | None = None
    enforced_global_model: str | None = None
    enable_usage_sharing: bool | None = None


# --- Import ---

class KiroUserMappingResponse(BaseModel):
    kiro_user_id: str
    email: str | None = None
    username: str | None = None
    imported_at: datetime | None = None

    model_config = {"from_attributes": True}

class ImportResult(BaseModel):
    imported: int
    updated: int
    errors: list[str]


# --- Pagination ---

class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# --- Analytics ---

class DailySeries(BaseModel):
    date: str
    credits: int


class UserCredit(BaseModel):
    user_id: int
    username: str
    credits: int


class TopUser(BaseModel):
    rank: int
    user_id: int
    username: str
    credits: int
    share_pct: float


class CreditShare(BaseModel):
    user_id: int
    username: str
    credits: int
    pct: float


class AnalyticsResponse(BaseModel):
    time_range: str
    daily_series: list[DailySeries]
    user_credits: list[UserCredit]
    top_users: list[TopUser]
    credit_share: list[CreditShare]
