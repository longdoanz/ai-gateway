"use client";

import { TrendingUp, Users, Key, Wallet } from "lucide-react";
import { useOverview } from "@/hooks/use-overview";
import { formatCredits } from "@/lib/utils";
import { AreaChartUsage } from "@/components/charts/area-chart-usage";
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
  const { data, isLoading } = useOverview();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
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
      <div>
        <h2 className="text-h1 font-bold text-on-surface tracking-tight">System Overview</h2>
        <p className="text-on-surface-variant mt-1 text-sm">Real-time credit consumption metrics</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <KpiCard
          title="Total Monthly Credits Consumed"
          value={formatCredits(data.total_credits_used)}
          subtitle="current billing cycle"
          icon={TrendingUp}
        />
        <KpiCard
          title="Active Users"
          value={data.active_users.toString()}
          subtitle="unique users this month"
          icon={Users}
        />
        <BudgetCard used={data.total_credits_used} limit={data.total_credits_limit} />
      </div>

      {/* Consumption Trend Chart */}
      <div className="glass-panel rounded-3xl p-6 flex flex-col h-[400px]">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-lg font-semibold text-on-surface">Credit Consumption Trend</h3>
            <p className="text-xs text-on-surface-variant mt-1">Daily usage over last 30 days</p>
          </div>
        </div>
        <div className="flex-1">
          <AreaChartUsage data={data.daily_usage} />
        </div>
      </div>

      {/* Active Keys stat */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <KpiCard
          title="Active API Keys"
          value={data.active_keys.toString()}
          subtitle="keys currently enabled"
          icon={Key}
        />
      </div>
    </div>
  );
}
