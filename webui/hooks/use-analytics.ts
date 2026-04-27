import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { AnalyticsResponse } from "@/lib/types";

export type AnalyticsRange = "7d" | "30d" | "90d";

export function useAnalytics(range: AnalyticsRange = "7d") {
  return useQuery({
    queryKey: ["analytics", range],
    queryFn: async () => {
      const res = await apiClient.get<AnalyticsResponse>(`/overview/analytics?range=${range}`);
      return res.data;
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
