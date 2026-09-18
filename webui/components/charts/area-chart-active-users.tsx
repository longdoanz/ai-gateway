"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ActiveUsersPoint } from "@/lib/types";

interface Props {
  data: ActiveUsersPoint[];
}

export function AreaChartActiveUsers({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="activeUsersGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4e1ee" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
          width={32}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
          formatter={(value) => [Number(value ?? 0).toLocaleString(), "Active Users"]}
        />
        <Area
          type="monotone"
          dataKey="count"
          stroke="#0ea5e9"
          strokeWidth={2}
          fill="url(#activeUsersGradient)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
