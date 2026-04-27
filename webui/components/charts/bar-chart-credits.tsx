"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { UserCredit } from "@/lib/types";
import { formatCredits } from "@/lib/utils";

interface Props {
  data: UserCredit[];
}

export function BarChartCredits({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
        No data for this period.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4e1ee" vertical={false} />
        <XAxis
          dataKey="username"
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => formatCredits(v)}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
          formatter={(value) => [formatCredits(Number(value ?? 0)), "Credits"]}
        />
        <Bar dataKey="credits" fill="#6366f1" radius={[6, 6, 0, 0]} barSize={40} />
      </BarChart>
    </ResponsiveContainer>
  );
}
