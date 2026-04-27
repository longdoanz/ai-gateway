import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { OverviewResponse } from "@/lib/types";

export type Granularity = "daily" | "weekly" | "monthly";

export function useOverview(granularity: Granularity = "daily") {
  return useQuery({
    queryKey: ["overview", granularity],
    queryFn: async () => {
      const res = await apiClient.get<OverviewResponse>("/overview", {
        params: { granularity },
      });
      return res.data;
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
