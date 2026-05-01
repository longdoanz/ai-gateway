"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalytics, type AnalyticsRange } from "@/hooks/use-analytics";
import { useKiroCreditUsage } from "@/hooks/use-kiro-credit-usage";
import { BarChartCredits } from "@/components/charts/bar-chart-credits";
import { AreaChartUsage } from "@/components/charts/area-chart-usage";
import { DonutChartShare } from "@/components/charts/donut-chart-share";
import { KiroCreditUsageTable } from "@/components/charts/kiro-credit-usage-table";
import { formatCredits } from "@/lib/utils";

const RANGES: AnalyticsRange[] = ["7d", "30d", "90d"];

export default function AnalyticsPage() {
  const [range, setRange] = useState<AnalyticsRange>("7d");
  const { data, isLoading, isError } = useAnalytics(range);
  const { data: creditData, isLoading: creditLoading, isError: creditError } = useKiroCreditUsage();

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <div className="glass-panel flex items-center rounded-xl p-1 gap-0.5">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`cursor-pointer px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                range === r
                  ? "bg-primary-container text-white shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container"
              }`}
            >
              {r.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Row 1: Bar + Area */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-3xl p-6">
          <h3 className="text-base font-semibold text-on-surface mb-4">User Credit Consumption</h3>
          <div className="h-[280px]">
            {isLoading ? (
              <Skeleton className="h-full w-full rounded-xl" />
            ) : isError ? (
              <ErrorState />
            ) : !data?.user_credits?.length ? (
              <EmptyState />
            ) : (
              <BarChartCredits data={data.user_credits} />
            )}
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h3 className="text-base font-semibold text-on-surface mb-4">Daily Credit Consumption</h3>
          <div className="h-[280px]">
            {isLoading ? (
              <Skeleton className="h-full w-full rounded-xl" />
            ) : isError ? (
              <ErrorState />
            ) : !data?.daily_series?.length ? (
              <EmptyState />
            ) : (
              <AreaChartUsage data={data.daily_series} />
            )}
          </div>
        </div>
      </div>

      {/* Row 2: Top Users + Donut */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-3xl p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-outline-variant/30">
            <h3 className="text-base font-semibold text-on-surface">Top Users</h3>
          </div>
          <div className="p-2">
            {isLoading ? (
              <div className="p-4 space-y-3">
                {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
              </div>
            ) : isError ? (
              <div className="p-6"><ErrorState /></div>
            ) : !data?.top_users?.length ? (
              <EmptyState />
            ) : (
              data.top_users.map((u) => (
                <div key={u.kiro_user_id} className="flex items-center justify-between p-3 rounded-xl hover:bg-surface-container transition-colors">
                  <div className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-full bg-primary-container flex items-center justify-center text-[10px] font-bold text-on-primary-container">
                      {u.rank}
                    </span>
                    <span className="text-sm font-medium text-on-surface">{u.display_name}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-primary">{formatCredits(u.credits)}</div>
                    <div className="text-[10px] text-on-surface-variant">{u.share_pct}%</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h3 className="text-base font-semibold text-on-surface mb-4">Credit Consume By Users</h3>
          <div className="h-[280px]">
            {isLoading ? (
              <Skeleton className="h-full w-full rounded-xl" />
            ) : isError ? (
              <ErrorState />
            ) : !data?.credit_share?.length ? (
              <EmptyState />
            ) : (
              <DonutChartShare data={data.credit_share} />
            )}
          </div>
        </div>
      </div>

      {/* Row 3: Kiro User Credit Usage */}
      <div className="glass-panel rounded-3xl p-0 overflow-hidden">
        <div className="px-6 py-4 border-b border-outline-variant/30 flex items-center justify-between">
          <h3 className="text-base font-semibold text-on-surface">Kiro User Credit Usage</h3>
          {creditData?.month && (
            <span className="text-xs text-on-surface-variant">{creditData.month}</span>
          )}
        </div>
        <div className="p-2">
          {creditLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
            </div>
          ) : creditError ? (
            <div className="p-6"><ErrorState /></div>
          ) : !creditData?.users?.length ? (
            <div className="p-6"><EmptyState /></div>
          ) : (
            <KiroCreditUsageTable data={creditData.users} />
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
      No data for this period.
    </div>
  );
}

function ErrorState() {
  return (
    <div className="flex items-center justify-center h-full text-error text-sm">
      Failed to load. Please refresh.
    </div>
  );
}
