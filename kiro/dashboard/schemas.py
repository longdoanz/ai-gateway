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


class GoogleLoginRequest(BaseModel):
    credential: str


# --- User ---

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdate(BaseModel):
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6)
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    can_create_gateway_key: bool | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
    can_create_gateway_key: bool = False

    model_config = {"from_attributes": True}


class ProvisionUserByEmail(BaseModel):
    email: str = Field(min_length=3, max_length=255)


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
    kiro_email: str | None = None
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
    input_tokens: int
    output_tokens: int


class OverviewResponse(BaseModel):
    total_input_tokens: int
    total_output_tokens: int
    total_credits_used: int
    total_credits_limit: int
    total_users: int
    active_users: int
    active_keys: int
    daily_usage: list[DailyUsage]
    total_gateway_users: int = 0
    active_gateway_users: int = 0
    gateway_input_tokens: int = 0
    gateway_output_tokens: int = 0


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
    is_active: bool = True

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
    input_tokens: int
    output_tokens: int


class UserTokenUsage(BaseModel):
    kiro_user_id: str
    display_name: str
    input_tokens: int
    output_tokens: int


class TopUser(BaseModel):
    rank: int
    kiro_user_id: str
    display_name: str
    input_tokens: int
    output_tokens: int
    share_pct: float


class TokenShare(BaseModel):
    kiro_user_id: str
    display_name: str
    input_tokens: int
    output_tokens: int
    pct: float


class AnalyticsResponse(BaseModel):
    time_range: str
    daily_series: list[DailySeries]
    user_tokens: list[UserTokenUsage]
    top_users: list[TopUser]
    token_share: list[TokenShare]


# --- Kiro User Credit Usage ---

class KiroUserCreditUsage(BaseModel):
    kiro_user_id: str
    display_name: str
    username: str | None = None
    email: str | None = None
    used_credit: int
    quota: int
    remaining: int
    remaining_pct: float
    shared_input_tokens: int = 0
    shared_output_tokens: int = 0


class KiroUserCreditUsageResponse(BaseModel):
    month: str
    users: list[KiroUserCreditUsage]


# --- GatewayKey ---

class GatewayKeyResponse(BaseModel):
    id: int
    user_id: int
    key_prefix: str
    key_suffix: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class GatewayKeyCreated(GatewayKeyResponse):
    raw_key: str  # shown only once at creation


# --- Gateway Key Analytics ---

class GatewayKeyDailySeries(BaseModel):
    date: str
    input_tokens: int
    output_tokens: int


class GatewayKeyUserUsage(BaseModel):
    gateway_key_id: int
    user_id: int
    username: str
    input_tokens: int
    output_tokens: int


class GatewayKeyAnalyticsResponse(BaseModel):
    time_range: str
    total_input_tokens: int
    total_output_tokens: int
    total_gateway_users: int
    active_gateway_users: int
    daily_series: list[GatewayKeyDailySeries]
    user_usages: list[GatewayKeyUserUsage]
