"use client";

import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DailySeries } from "@/lib/types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

interface Props {
  data: DailySeries[];
}

export function AreaChartUsage({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="inputGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="outputGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
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
          formatter={(value, name) => [formatTokens(Number(value ?? 0)), name === "input_tokens" ? "Input" : "Output"]}
        />
        <Legend formatter={(value) => (value === "input_tokens" ? "Input Tokens" : "Output Tokens")} />
        <Area
          type="monotone"
          dataKey="input_tokens"
          stroke="#0ea5e9"
          strokeWidth={2}
          fill="url(#inputGradient)"
        />
        <Area
          type="monotone"
          dataKey="output_tokens"
          stroke="#8b5cf6"
          strokeWidth={2}
          fill="url(#outputGradient)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
