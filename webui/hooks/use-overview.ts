import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { OverviewResponse } from "@/lib/types";

export function useOverview() {
  return useQuery({
    queryKey: ["overview"],
    queryFn: async () => {
      const res = await apiClient.get<OverviewResponse>("/overview");
      return res.data;
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
