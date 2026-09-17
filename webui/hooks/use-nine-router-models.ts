import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { NineRouterModelsResponse } from "@/lib/types";

export function useNineRouterModels() {
  return useQuery({
    queryKey: ["nine-router-models"],
    queryFn: async () => {
      const res = await apiClient.get<NineRouterModelsResponse>("/nine-router/models");
      return res.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes — catalog changes rarely
  });
}
