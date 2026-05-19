import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { ApiKeyResponse, SystemKeyCreate, SystemKeyUpdate } from "@/lib/types";

export function useSystemKeys(limit = 50, offset = 0) {
  return useQuery({
    queryKey: ["system-keys", limit, offset],
    queryFn: async () => {
      const res = await apiClient.get<ApiKeyResponse[]>("/system-keys", { params: { limit, offset } });
      return res.data;
    },
    refetchInterval: 60_000,
  });
}

export interface SystemKeyPoolEntry {
  key_id: number;
  is_active: boolean;
  use_proxy: boolean;
  current_usage: number;
  usage_limit: number;
  remaining: number | null;
  quota_exhausted_for_seconds: number | null;
}

export interface StickyBinding {
  gateway_key_id: number;
  system_key_id: number;
  expires_in_seconds: number;
  is_active: boolean | null;
  current_usage: number | null;
  usage_limit: number | null;
}

export function useSystemKeyPool() {
  return useQuery({
    queryKey: ["system-keys-pool"],
    queryFn: async () => {
      const res = await apiClient.get<SystemKeyPoolEntry[]>("/system-keys/debug/pool");
      return res.data;
    },
    refetchInterval: 10_000,
  });
}

export function useStickyBindings() {
  return useQuery({
    queryKey: ["system-keys-bindings"],
    queryFn: async () => {
      const res = await apiClient.get<StickyBinding[]>("/system-keys/debug/bindings");
      return res.data;
    },
    refetchInterval: 10_000,
  });
}

export function useCreateSystemKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: SystemKeyCreate) => {
      const res = await apiClient.post<ApiKeyResponse>("/system-keys", data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["system-keys"] }),
  });
}

export function useUpdateSystemKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ keyId, data }: { keyId: number; data: SystemKeyUpdate }) => {
      const res = await apiClient.put<ApiKeyResponse>(`/system-keys/${keyId}`, data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["system-keys"] }),
  });
}

export function useDeleteSystemKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (keyId: number) => {
      await apiClient.delete(`/system-keys/${keyId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["system-keys"] }),
  });
}
