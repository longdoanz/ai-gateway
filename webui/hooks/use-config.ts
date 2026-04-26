import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { SystemConfigResponse, SystemConfigUpdate } from "@/lib/types";

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: async () => {
      const res = await apiClient.get<SystemConfigResponse>("/config");
      return res.data;
    },
  });
}

export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: SystemConfigUpdate) => {
      const res = await apiClient.put<SystemConfigResponse>("/config", data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config"] }),
  });
}
