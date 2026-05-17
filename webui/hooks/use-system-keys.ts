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
