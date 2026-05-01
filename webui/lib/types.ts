// --- Auth ---

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface GoogleLoginRequest {
  credential: string;
}

export interface JwtPayload {
  sub: string;
  role: "admin" | "user";
  username: string;
  can_create_gateway_key: boolean;
  exp: number;
  type: "access" | "refresh";
}

// --- User ---

export interface UserCreate {
  username: string;
  password: string;
  role?: "admin" | "user";
}

export interface UserUpdate {
  is_active?: boolean;
  password?: string;
  role?: "admin" | "user";
  can_create_gateway_key?: boolean;
}

export interface UserResponse {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
  can_create_gateway_key: boolean;
}

export interface UserDetailResponse extends UserResponse {
  api_keys: ApiKeyResponse[];
}

// --- ApiKey ---

export interface ApiKeyCreate {
  raw_key: string;
  user_id?: number;
}

export interface ApiKeyResponse {
  id: number;
  user_id: number;
  kiro_user_id: string | null;
  kiro_email: string | null;
  key_prefix: string;
  key_suffix: string;
  is_active: boolean;
  created_at: string;
}

export interface ApiKeyToggle {
  is_active: boolean;
}

// --- KeyUsage ---

export interface KeyUsageResponse {
  month: string;
  current_usage: number;
  usage_limit: number;
  last_synced_at: string | null;
  last_used_at: string | null;
}

// --- Overview ---

export interface DailyUsage {
  date: string;
  credits: number;
}

export interface OverviewResponse {
  total_credits_used: number;
  total_credits_limit: number;
  total_users: number;
  active_users: number;
  active_keys: number;
  daily_usage: DailyUsage[];
  total_gateway_users: number;
  active_gateway_users: number;
  gateway_credits_used: number;
}

// --- Config ---

export interface SystemConfigResponse {
  enable_model_override: boolean;
  enforced_global_model: string;
  enable_usage_sharing: boolean;
}

export interface SystemConfigUpdate {
  enable_model_override?: boolean;
  enforced_global_model?: string;
  enable_usage_sharing?: boolean;
}

// --- Import ---

export interface ImportResult {
  imported: number;
  updated: number;
  errors: string[];
}

// --- Analytics ---

export interface DailySeries {
  date: string;
  credits: number;
}

export interface UserCredit {
  kiro_user_id: string;
  display_name: string;
  credits: number;
}

export interface TopUser {
  rank: number;
  kiro_user_id: string;
  display_name: string;
  credits: number;
  share_pct: number;
}

export interface CreditShare {
  kiro_user_id: string;
  display_name: string;
  credits: number;
  pct: number;
}

export interface AnalyticsResponse {
  time_range: string;
  daily_series: DailySeries[];
  user_credits: UserCredit[];
  top_users: TopUser[];
  credit_share: CreditShare[];
}

// --- Kiro User Credit Usage ---

export interface KiroUserCreditUsage {
  kiro_user_id: string;
  username: string | null;
  email: string | null;
  used_credit: number;
  quota: number;
  remaining: number;
  remaining_pct: number;
  shared_usage: number;
}

export interface KiroUserCreditUsageResponse {
  month: string;
  users: KiroUserCreditUsage[];
}

// --- GatewayKey ---

export interface GatewayKeyResponse {
  id: number;
  user_id: number;
  key_prefix: string;
  key_suffix: string;
  is_active: boolean;
  created_at: string;
}

export interface GatewayKeyCreated extends GatewayKeyResponse {
  raw_key: string;
}

// --- Gateway Key Analytics ---

export interface GatewayKeyDailySeries {
  date: string;
  credits: number;
}

export interface GatewayKeyUserUsage {
  gateway_key_id: number;
  user_id: number;
  username: string;
  credits: number;
}

export interface GatewayKeyAnalyticsResponse {
  time_range: string;
  total_credits: number;
  total_gateway_users: number;
  active_gateway_users: number;
  daily_series: GatewayKeyDailySeries[];
  user_usages: GatewayKeyUserUsage[];
}
