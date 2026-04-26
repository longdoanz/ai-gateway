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

export interface JwtPayload {
  sub: string;
  role: "admin" | "user";
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
}

export interface UserResponse {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface UserDetailResponse extends UserResponse {
  api_keys: ApiKeyResponse[];
}

// --- ApiKey ---

export interface ApiKeyCreate {
  raw_key: string;
}

export interface ApiKeyResponse {
  id: number;
  user_id: number;
  kiro_user_id: string | null;
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
  active_users: number;
  active_keys: number;
  daily_usage: DailyUsage[];
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
