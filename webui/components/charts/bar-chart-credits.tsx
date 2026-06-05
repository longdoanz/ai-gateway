"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { UserTokenUsage } from "@/lib/types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

interface Props {
  data: UserTokenUsage[];
}

export function BarChartTokens({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
        No data for this period.
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    label: d.username ?? d.display_name,
  }));

  const needsRotation = chartData.length > 6;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: needsRotation ? 60 : 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4e1ee" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
          angle={needsRotation ? -35 : 0}
          textAnchor={needsRotation ? "end" : "middle"}
          interval={0}
        />
        <YAxis
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => formatTokens(v)}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
          labelFormatter={(label) => label}
          formatter={(value, name) => [formatTokens(Number(value ?? 0)), name === "input_tokens" ? "Input" : "Output"]}
        />
        <Legend formatter={(value) => (value === "input_tokens" ? "Input Tokens" : "Output Tokens")} />
        <Bar dataKey="input_tokens" fill="#6366f1" radius={[6, 6, 0, 0]} barSize={20} />
        <Bar dataKey="output_tokens" fill="#8b5cf6" radius={[6, 6, 0, 0]} barSize={20} />
      </BarChart>
    </ResponsiveContainer>
  );
}
