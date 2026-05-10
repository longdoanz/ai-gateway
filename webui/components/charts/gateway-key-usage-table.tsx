"use client";

import type { GatewayKeyUserUsage } from "@/lib/types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

export function GatewayKeyUsageTable({ data }: { data: GatewayKeyUserUsage[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-on-surface-variant text-xs border-b border-outline-variant/30">
            <th className="text-left px-4 py-3 font-medium">User</th>
            <th className="text-right px-4 py-3 font-medium">Input Tokens</th>
            <th className="text-right px-4 py-3 font-medium">Output Tokens</th>
          </tr>
        </thead>
        <tbody>
          {data.map((user) => (
            <tr
              key={user.gateway_key_id}
              className="border-b border-outline-variant/10 hover:bg-surface-container transition-colors"
            >
              <td className="px-4 py-3 font-medium text-on-surface">{user.username}</td>
              <td className="text-right px-4 py-3 text-on-surface">{formatTokens(user.input_tokens)}</td>
              <td className="text-right px-4 py-3 text-on-surface-variant">{formatTokens(user.output_tokens)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
