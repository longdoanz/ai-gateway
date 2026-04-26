import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { ApiKeyCreate, ApiKeyResponse, KeyUsageResponse } from "@/lib/types";

export function useKeys(limit = 50, offset = 0) {
  return useQuery({
    queryKey: ["keys", limit, offset],
    queryFn: async () => {
      const res = await apiClient.get<ApiKeyResponse[]>("/keys", { params: { limit, offset } });
      return res.data;
    },
    refetchInterval: 60_000,
  });
}

export function useKeyUsage(keyId: number | null) {
  return useQuery({
    queryKey: ["keys", keyId, "usage"],
    queryFn: async () => {
      const res = await apiClient.get<KeyUsageResponse[]>(`/keys/${keyId}/usage`);
      return res.data;
    },
    enabled: keyId !== null,
  });
}

export function useCreateKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: ApiKeyCreate) => {
      const res = await apiClient.post<ApiKeyResponse>("/keys", data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });
}

export function useToggleKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ keyId, isActive }: { keyId: number; isActive: boolean }) => {
      const res = await apiClient.put<ApiKeyResponse>(`/keys/${keyId}`, { is_active: isActive });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });
}

export function useDeleteKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (keyId: number) => {
      await apiClient.delete(`/keys/${keyId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });
}
