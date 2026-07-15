"use client";

import type { GatewayKeyUserUsage } from "@/lib/types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function formatLastActive(iso: string | null): string {
  if (!iso) return "Never";
  // Backend stores naive UTC timestamps; ensure they are parsed as UTC.
  const ts = iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`;
  const then = new Date(ts).getTime();
  if (Number.isNaN(then)) return "—";
  const diffMs = Date.now() - then;
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  const mon = Math.floor(day / 30);
  if (mon < 12) return `${mon}mo ago`;
  return `${Math.floor(mon / 12)}y ago`;
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
            <th className="text-right px-4 py-3 font-medium">Last Active</th>
          </tr>
        </thead>
        <tbody>
          {data.map((user) => {
            const inactive = !user.input_tokens && !user.output_tokens;
            return (
              <tr
                key={user.user_id}
                className="border-b border-outline-variant/10 hover:bg-surface-container transition-colors"
              >
                <td className="px-4 py-3 font-medium text-on-surface">
                  {user.username}
                  {inactive && (
                    <span className="ml-2 text-xs text-on-surface-variant">(idle)</span>
                  )}
                </td>
                <td className="text-right px-4 py-3 text-on-surface">{formatTokens(user.input_tokens)}</td>
                <td className="text-right px-4 py-3 text-on-surface-variant">{formatTokens(user.output_tokens)}</td>
                <td
                  className="text-right px-4 py-3 text-on-surface-variant"
                  title={user.last_active_at ?? undefined}
                >
                  {formatLastActive(user.last_active_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
