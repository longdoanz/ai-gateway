"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { useKeys } from "@/hooks/use-keys";
import { useUsers } from "@/hooks/use-users";
import { BarChartUsers } from "@/components/charts/bar-chart-users";

export default function AnalyticsPage() {
  const { data: users, isLoading: usersLoading } = useUsers();
  const { data: keys, isLoading: keysLoading } = useKeys();
  const isLoading = usersLoading || keysLoading;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-h1 font-bold text-on-surface tracking-tight">Usage Analytics</h1>
        <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">Credit consumption breakdown by user.</p>
      </div>

      {isLoading ? (
        <Skeleton className="h-[400px] rounded-3xl" />
      ) : (
        <div className="glass-panel rounded-3xl p-6 h-[400px]">
          <h3 className="text-lg font-semibold text-on-surface mb-4">User Credit Consumption</h3>
          <div className="h-[320px]"><BarChartUsers users={users || []} keys={keys || []} /></div>
        </div>
      )}
    </div>
  );
}
