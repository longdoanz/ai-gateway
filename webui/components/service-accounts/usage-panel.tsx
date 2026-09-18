"use client";

import { useMemo, useState } from "react";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { BarChartServiceAccountDaily } from "@/components/charts/bar-chart-service-account-daily";
import { useServiceAccountUsage } from "@/hooks/use-service-accounts";
import { formatCredits, formatDate } from "@/lib/utils";

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white/70 border border-black/5 rounded-xl p-4">
      <div className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider">{label}</div>
      <div className="text-2xl font-mono font-bold text-on-surface mt-1">{value}</div>
    </div>
  );
}

export function UsagePanel({ accountId }: { accountId: number }) {
  const [days, setDays] = useState("30");
  const { data: usage, isLoading } = useServiceAccountUsage(accountId, parseInt(days, 10));

  const dailyTotals = useMemo(() => {
    if (!usage) return [];
    const totals = new Map<string, number>();
    for (const d of usage.daily) {
      totals.set(d.date, (totals.get(d.date) ?? 0) + d.input_tokens + d.output_tokens);
    }
    return Array.from(totals.entries())
      .map(([date, total]) => ({ date, total }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [usage]);

  const periodTotal = dailyTotals.reduce((sum, d) => sum + d.total, 0);
  const activeDays = dailyTotals.filter((d) => d.total > 0).length;
  const modelsUsed = new Set(usage?.daily.map((d) => d.model) ?? []).size;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Label className="text-xs text-on-surface-variant">Window</Label>
        <Select value={days} onValueChange={(v) => setDays(v ?? "30")}>
          <SelectTrigger size="sm" className="w-28"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 days</SelectItem>
            <SelectItem value="30">30 days</SelectItem>
            <SelectItem value="90">90 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => (<Skeleton key={i} className="h-10 rounded-lg" />))}</div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatTile label="Tokens in window" value={formatCredits(periodTotal)} />
            <StatTile label="Active days" value={`${activeDays} / ${dailyTotals.length}`} />
            <StatTile label="Models used" value={String(modelsUsed)} />
          </div>

          <div>
            <h4 className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">
              Daily Usage Trend
            </h4>
            <div className="h-64 border border-outline-variant/40 rounded-xl bg-white/60 p-2">
              <BarChartServiceAccountDaily data={dailyTotals} />
            </div>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Monthly Rollup</h4>
            {usage && usage.monthly.length > 0 ? (
              <div className="border border-outline-variant/40 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-container-low/50">
                    <tr>
                      <th className="py-2 px-3 font-medium text-on-surface-variant">Month</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Usage</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Last Used</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/20">
                    {usage.monthly.map((m) => (
                      <tr key={m.month}>
                        <td className="py-2 px-3 font-mono">{m.month}</td>
                        <td className="py-2 px-3 text-right font-mono">{formatCredits(m.current_usage)}</td>
                        <td className="py-2 px-3 text-right text-on-surface-variant">
                          {m.last_used_at ? formatDate(m.last_used_at) : "never"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-on-surface-variant py-3">No usage recorded yet.</p>
            )}
          </div>

          <div>
            <h4 className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">
              Daily Breakdown by Model
            </h4>
            {usage && usage.daily.length > 0 ? (
              <div className="border border-outline-variant/40 rounded-lg overflow-hidden max-h-96 overflow-y-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-container-low/50 sticky top-0">
                    <tr>
                      <th className="py-2 px-3 font-medium text-on-surface-variant">Date</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant">Model</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Input</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Output</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/20">
                    {usage.daily.map((d, i) => (
                      <tr key={`${d.date}-${d.model}-${i}`}>
                        <td className="py-2 px-3">{d.date}</td>
                        <td className="py-2 px-3 font-mono">{d.model}</td>
                        <td className="py-2 px-3 text-right font-mono">{formatCredits(d.input_tokens)}</td>
                        <td className="py-2 px-3 text-right font-mono">{formatCredits(d.output_tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-on-surface-variant py-3">No daily usage in this window.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
