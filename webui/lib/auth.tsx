"use client";

import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import type { JwtPayload, LoginRequest, TokenResponse } from "@/lib/types";
import apiClient, { clearTokens, getStoredRefreshToken, setTokens } from "@/lib/api-client";

export interface AuthUser {
  id: number;
  role: "admin" | "user";
  username: string;
  can_create_gateway_key: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  loginWithGoogle: (credential: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  login: async () => {},
  loginWithGoogle: async () => {},
  logout: () => {},
});

function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const base64 = token.split(".")[1];
    const json = atob(base64.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function userFromToken(token: string): AuthUser | null {
  const payload = decodeJwtPayload(token);
  if (!payload || payload.type !== "access") return null;
  if (payload.exp * 1000 < Date.now()) return null;
  return {
    id: parseInt(payload.sub),
    role: payload.role,
    username: payload.username || "",
    can_create_gateway_key: payload.can_create_gateway_key ?? false,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const rt = getStoredRefreshToken();
    if (!rt) {
      setIsLoading(false);
      return;
    }
    apiClient
      .post<TokenResponse>("/auth/refresh", { refresh_token: rt })
      .then((res) => {
        setTokens(res.data.access_token, res.data.refresh_token);
        setUser(userFromToken(res.data.access_token));
      })
      .catch(() => {
        clearTokens();
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (credentials: LoginRequest) => {
    const res = await apiClient.post<TokenResponse>("/auth/login", credentials);
    setTokens(res.data.access_token, res.data.refresh_token);
    setUser(userFromToken(res.data.access_token));
  }, []);

  const loginWithGoogle = useCallback(async (credential: string) => {
    const res = await apiClient.post<TokenResponse>("/auth/google", { credential });
    setTokens(res.data.access_token, res.data.refresh_token);
    setUser(userFromToken(res.data.access_token));
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, login, loginWithGoogle, logout }),
    [user, isLoading, login, loginWithGoogle, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
