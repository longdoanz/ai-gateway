"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCredits } from "@/lib/utils";

interface Props {
  data: { date: string; total: number }[];
}

export function BarChartServiceAccountDaily({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
        No usage recorded in this window.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
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
          tickFormatter={(v) => formatCredits(Number(v))}
          width={48}
        />
        <Tooltip
          cursor={{ fill: "#6366f1", fillOpacity: 0.06 }}
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
            fontSize: 12,
          }}
          labelFormatter={(label) => label}
          formatter={(value) => [formatCredits(Number(value ?? 0)), "Tokens"]}
        />
        <Bar dataKey="total" name="Tokens" fill="#6366f1" radius={[6, 6, 0, 0]} maxBarSize={28} />
      </BarChart>
    </ResponsiveContainer>
  );
}
