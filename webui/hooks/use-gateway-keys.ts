import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { GatewayKeyCreated, GatewayKeyResponse } from "@/lib/types";

export function useGatewayKey() {
  return useQuery({
    queryKey: ["gateway-key"],
    queryFn: async () => {
      const res = await apiClient.get<GatewayKeyResponse | null>("/gateway-keys/me");
      return res.data;
    },
  });
}

export function useCreateGatewayKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await apiClient.post<GatewayKeyCreated>("/gateway-keys/me");
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gateway-key"] }),
  });
}

export function useRevokeGatewayKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiClient.delete("/gateway-keys/me");
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gateway-key"] }),
  });
}
