"use client";

import { useState } from "react";
import { TrendingUp, Users, Key, Wallet, KeyRound } from "lucide-react";
import { useOverview, type Granularity } from "@/hooks/use-overview";
import { formatCredits } from "@/lib/utils";
import { AreaChartUsage } from "@/components/charts/area-chart-usage";
import { AreaChartCreditTrend } from "@/components/charts/area-chart-credit-trend";
import { Skeleton } from "@/components/ui/skeleton";

function KpiCard({
  title,
  value,
  subtitle,
  icon: Icon,
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ElementType;
}) {
  return (
    <div className="glass-panel rounded-3xl p-6 relative overflow-hidden group">
      <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-3xl opacity-0 group-hover:opacity-50 -mr-10 -mt-10 pointer-events-none transition-opacity duration-500" />
      <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
        <Icon className="w-16 h-16 text-primary" />
      </div>
      <h3 className="text-sm font-medium text-on-surface-variant mb-1">{title}</h3>
      <div className="flex items-end gap-3 mt-4">
        <span className="text-4xl font-bold text-on-surface tracking-tight font-mono">{value}</span>
      </div>
      <p className="text-xs text-on-surface-variant mt-2">{subtitle}</p>
    </div>
  );
}

function BudgetCard({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.round((used / limit) * 100) : 0;
  const remaining = limit - used;

  return (
    <div className="glass-panel-elevated rounded-3xl p-6 relative overflow-hidden group border-primary/20">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-50" />
      <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
        <Wallet className="w-16 h-16 text-primary" />
      </div>
      <h3 className="text-sm font-medium text-primary mb-1 relative z-10">Remaining Budget</h3>
      <div className="flex items-end gap-3 mt-4 relative z-10">
        <span className="text-4xl font-bold text-on-surface tracking-tight font-mono">
          {formatCredits(remaining)}
        </span>
        <span className="text-sm text-on-surface-variant mb-1">Credits</span>
      </div>
      <div className="mt-4 relative z-10">
        <div className="flex justify-between text-xs mb-1 text-on-surface-variant">
          <span>Usage</span>
          <span>{pct}%</span>
        </div>
        <div className="w-full bg-surface-container-high rounded-full h-1.5 overflow-hidden">
          <div
            className="bg-primary h-1.5 rounded-full shadow-[0_0_8px_rgba(14,165,233,0.4)]"
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const { data, isLoading } = useOverview(granularity);

  const granularityOptions: { value: Granularity; label: string }[] = [
    { value: "daily", label: "Daily" },
    { value: "weekly", label: "Weekly" },
    { value: "monthly", label: "Monthly" },
  ];

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-40 rounded-2xl" />
          ))}
        </div>
        <Skeleton className="h-[400px] rounded-2xl" />
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-8">
      {/* KPI Cards — 4 on first row, 2 on second */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KpiCard
          title="Total Users"
          value={String(data.total_users ?? 0)}
          subtitle="Kiro users with active keys"
          icon={Users}
        />
        <KpiCard
          title="Active Users"
          value={String(data.active_users ?? 0)}
          subtitle="unique users this month"
          icon={Users}
        />
        <KpiCard
          title="Active API Keys"
          value={data.active_keys.toString()}
          subtitle="keys currently enabled"
          icon={Key}
        />
        <KpiCard
          title="Gateway Key Users"
          value={String(data.total_gateway_users ?? 0)}
          subtitle={`${data.active_gateway_users ?? 0} active this month`}
          icon={KeyRound}
        />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <KpiCard
          title="Total Monthly Credits Consumed"
          value={formatCredits(data.total_credits_used)}
          subtitle="current billing cycle"
          icon={TrendingUp}
        />
        <BudgetCard used={data.total_credits_used} limit={data.total_credits_limit} />
      </div>

      {/* Credit Consumption Trend Chart */}
      <div className="glass-panel rounded-3xl p-6 flex flex-col h-[400px]">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-lg font-semibold text-on-surface">Credit Consumption Trend</h3>
            <p className="text-xs text-on-surface-variant mt-1">
              Daily credits consumed (delta from previous day)
            </p>
          </div>
        </div>
        <div className="h-[280px]">
          {data.credit_trend && data.credit_trend.length > 0 ? (
            <AreaChartCreditTrend data={data.credit_trend} />
          ) : (
            <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
              No credit snapshot data yet. Data will appear after the first sync.
            </div>
          )}
        </div>
      </div>

      {/* Token Usage Trend Chart */}
      <div className="glass-panel rounded-3xl p-6 flex flex-col h-[400px]">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-lg font-semibold text-on-surface">Token Usage Trend</h3>
            <p className="text-xs text-on-surface-variant mt-1">
              {granularity === "daily" && "Daily usage this month"}
              {granularity === "weekly" && "Weekly usage (last 90 days)"}
              {granularity === "monthly" && "Monthly usage (last 6 months)"}
            </p>
          </div>
          <div className="flex gap-1 bg-surface-container rounded-xl p-1">
            {granularityOptions.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setGranularity(opt.value)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  granularity === opt.value
                    ? "bg-primary text-on-primary shadow-sm"
                    : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="h-[280px]">
          <AreaChartUsage data={data.daily_usage} />
        </div>
      </div>

    </div>
  );
}
