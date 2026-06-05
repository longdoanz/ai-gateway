"use client";

import { useState } from "react";
import { LineChart, Line, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { UserDailySeries } from "@/lib/types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

const COLORS = [
  "#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
  "#06b6d4", "#a855f7", "#84cc16", "#f97316", "#ec4899",
];

interface Props {
  data: UserDailySeries[];
}

export function LineChartUserDaily({ data }: Props) {
  const [highlighted, setHighlighted] = useState<string | null>(null);

  if (!data.length) return null;

  const userLabels = data.map((u) => u.username ?? u.display_name);
  const dataKeys = data.map((_, idx) => `user_${idx}`);

  const dates = data[0].daily.map((d) => d.date);
  const chartData = dates.map((date, i) => {
    const point: Record<string, string | number> = { date };
    for (let j = 0; j < data.length; j++) {
      const d = data[j].daily[i];
      point[dataKeys[j]] = d ? d.input_tokens + d.output_tokens : 0;
    }
    return point;
  });

  const handleLegendClick = (e: { dataKey?: string | number | ((obj: unknown) => unknown) }) => {
    const key = typeof e?.dataKey === "string" ? e.dataKey : undefined;
    if (!key) return;
    setHighlighted((prev) => (prev === key ? null : key));
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4e1ee" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => formatTokens(v)}
          width={48}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
          formatter={(value, name) => {
            const idx = dataKeys.indexOf(String(name));
            const label = userLabels[idx] ?? String(name);
            return [formatTokens(Number(value ?? 0)), label];
          }}
        />
        <Legend
          wrapperStyle={{ fontSize: 11, cursor: "pointer" }}
          onClick={handleLegendClick}
        />
        {data.map((_, idx) => {
          const key = dataKeys[idx];
          const isActive = highlighted === null || highlighted === key;
          return (
            <Line
              key={key}
              name={userLabels[idx]}
              type="monotone"
              dataKey={key}
              stroke={COLORS[idx % COLORS.length]}
              strokeWidth={highlighted === key ? 3 : 2}
              strokeOpacity={isActive ? 1 : 0.15}
              dot={false}
              activeDot={isActive ? { r: 4 } : false}
            />
          );
        })}
      </LineChart>
    </ResponsiveContainer>
  );
}
