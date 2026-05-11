"use client";

import type { KiroUserCreditUsage } from "@/lib/types";
import { formatCredits } from "@/lib/utils";

function remainingColor(pct: number): string {
  if (pct > 50) return "text-green-400";
  if (pct >= 20) return "text-yellow-400";
  return "text-red-400";
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function displayName(user: KiroUserCreditUsage): string {
  return user.display_name || user.username || user.email || user.kiro_user_id;
}

export function KiroCreditUsageTable({ data }: { data: KiroUserCreditUsage[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-on-surface-variant text-xs border-b border-outline-variant/30">
            <th className="text-left px-4 py-3 font-medium">User</th>
            <th className="text-right px-4 py-3 font-medium">Used (credits)</th>
            <th className="text-right px-4 py-3 font-medium">Quota (credits)</th>
            <th className="text-right px-4 py-3 font-medium">Remaining (credits)</th>
            <th className="text-right px-4 py-3 font-medium">Remaining %</th>
            <th className="text-right px-4 py-3 font-medium">Shared In (tokens)</th>
            <th className="text-right px-4 py-3 font-medium">Shared Out (tokens)</th>
          </tr>
        </thead>
        <tbody>
          {data.map((user) => (
            <tr
              key={user.kiro_user_id}
              className="border-b border-outline-variant/10 hover:bg-surface-container transition-colors"
            >
              <td className="px-4 py-3 font-medium text-on-surface">
                {displayName(user)}
              </td>
              <td className="text-right px-4 py-3 text-on-surface">
                {formatCredits(user.used_credit)}
              </td>
              <td className="text-right px-4 py-3 text-on-surface-variant">
                {formatCredits(user.quota)}
              </td>
              <td className="text-right px-4 py-3 text-on-surface">
                {formatCredits(user.remaining)}
              </td>
              <td className={`text-right px-4 py-3 font-semibold ${remainingColor(user.remaining_pct)}`}>
                {user.remaining_pct.toFixed(1)}%
              </td>
              <td className="text-right px-4 py-3 text-on-surface-variant">
                {user.shared_input_tokens > 0 ? formatTokens(user.shared_input_tokens) : "—"}
              </td>
              <td className="text-right px-4 py-3 text-on-surface-variant">
                {user.shared_output_tokens > 0 ? formatTokens(user.shared_output_tokens) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
