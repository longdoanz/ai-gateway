"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { TokenShare } from "@/lib/types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

const COLORS = [
  "#6366f1", "#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b",
  "#ef4444", "#ec4899", "#14b8a6", "#f97316", "#84cc16",
];

interface Props {
  data: TokenShare[];
}

export function DonutChartShare({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
        No data for this period.
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    total_tokens: d.input_tokens + d.output_tokens,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={chartData}
          dataKey="total_tokens"
          nameKey="display_name"
          cx="38%"
          cy="50%"
          innerRadius="55%"
          outerRadius="85%"
          paddingAngle={2}
        >
          {chartData.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
          formatter={(value, name, props) => [
            `${formatTokens(Number(value))} (${props.payload.pct}%)`,
            name,
          ]}
        />
        <Legend
          layout="vertical"
          align="right"
          verticalAlign="middle"
          iconType="circle"
          iconSize={8}
          formatter={(value) => (
            <span style={{ fontSize: 12, color: "#464555" }}>{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
