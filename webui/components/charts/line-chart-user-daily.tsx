"use client";

import { useState } from "react";
import { LineChart, Line, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ComponentProps } from "react";
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

  const renderTooltip = (props: {
    active?: boolean;
    payload?: Array<{ dataKey?: string | number; value?: number; color?: string }>;
    label?: string;
  }) => {
    const { active, payload, label } = props;
    if (!active || !payload?.length) return null;

    let rows = payload
      .map((entry) => {
        const key = String(entry.dataKey);
        const idx = dataKeys.indexOf(key);
        return {
          key,
          name: userLabels[idx] ?? key,
          color: entry.color,
          value: Number(entry.value ?? 0),
        };
      })
      .filter((r) => (highlighted ? r.key === highlighted : r.value > 0))
      .sort((a, b) => b.value - a.value);

    if (!rows.length) return null;

    return (
      <div
        style={{
          background: "rgba(255,255,255,0.85)",
          backdropFilter: "blur(16px)",
          border: "1px solid rgba(255,255,255,0.9)",
          borderRadius: "12px",
          boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          padding: "8px 12px",
          fontSize: 11,
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 6, color: "#464555" }}>{label}</div>
        <div style={{ maxHeight: 220, overflowY: "auto", paddingRight: 4 }}>
          {rows.map((r) => (
            <div
              key={r.key}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "1px 0" }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: r.color,
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  color: "#464555",
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {r.name}
              </span>
              <span style={{ fontWeight: 600, color: "#1a1a2e" }}>{formatTokens(r.value)}</span>
            </div>
          ))}
        </div>
      </div>
    );
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
        <Tooltip cursor={{ stroke: "#c9c5d6", strokeWidth: 1 }} content={renderTooltip as unknown as ComponentProps<typeof Tooltip>["content"]} />
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
