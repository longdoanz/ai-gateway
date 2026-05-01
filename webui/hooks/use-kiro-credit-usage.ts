import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { KiroUserCreditUsageResponse } from "@/lib/types";

export function useKiroCreditUsage(month?: string) {
  return useQuery({
    queryKey: ["kiro-credit-usage", month],
    queryFn: async () => {
      const params = month ? `?month=${month}` : "";
      const res = await apiClient.get<KiroUserCreditUsageResponse>(
        `/overview/analytics/kiro-credit-usage${params}`
      );
      return res.data;
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
