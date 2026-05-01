import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { GatewayKeyAnalyticsResponse } from "@/lib/types";

export type GatewayKeyAnalyticsRange = "7d" | "30d" | "90d";

export function useGatewayKeyAnalytics(range: GatewayKeyAnalyticsRange = "7d") {
  return useQuery({
    queryKey: ["gateway-key-analytics", range],
    queryFn: async () => {
      const res = await apiClient.get<GatewayKeyAnalyticsResponse>(
        `/overview/analytics/gateway-key-usage?range=${range}`
      );
      return res.data;
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
