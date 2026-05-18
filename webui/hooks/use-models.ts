import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { ModelListResponse } from "@/lib/types";

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const res = await apiClient.get<ModelListResponse>("/models");
      return res.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes — model list changes rarely
  });
}
