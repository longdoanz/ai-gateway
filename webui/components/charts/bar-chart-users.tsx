"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ApiKeyResponse, UserResponse } from "@/lib/types";

interface Props {
  users: UserResponse[];
  keys: ApiKeyResponse[];
}

export function BarChartUsers({ users, keys }: Props) {
  const data = users.map((u) => ({
    name: u.username,
    keys: keys.filter((k) => k.user_id === u.id && k.is_active).length,
  }));

  if (data.length === 0) {
    return (<div className="flex items-center justify-center h-full text-on-surface-variant">No user data available.</div>);
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4e1ee" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#464555" }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 12, fill: "#464555" }} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={{ background: "rgba(255,255,255,0.85)", backdropFilter: "blur(16px)", border: "1px solid rgba(255,255,255,0.9)", borderRadius: "12px", boxShadow: "0 8px 30px rgba(0,0,0,0.05)" }} />
        <Bar dataKey="keys" fill="#6366f1" radius={[6, 6, 0, 0]} barSize={40} />
      </BarChart>
    </ResponsiveContainer>
  );
}
