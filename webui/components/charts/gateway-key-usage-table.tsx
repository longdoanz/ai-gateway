"use client";

import type { GatewayKeyUserUsage } from "@/lib/types";
import { formatCredits } from "@/lib/utils";

export function GatewayKeyUsageTable({ data }: { data: GatewayKeyUserUsage[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-on-surface-variant text-xs border-b border-outline-variant/30">
            <th className="text-left px-4 py-3 font-medium">User</th>
            <th className="text-right px-4 py-3 font-medium">Credits Used</th>
          </tr>
        </thead>
        <tbody>
          {data.map((user) => (
            <tr
              key={user.gateway_key_id}
              className="border-b border-outline-variant/10 hover:bg-surface-container transition-colors"
            >
              <td className="px-4 py-3 font-medium text-on-surface">{user.username}</td>
              <td className="text-right px-4 py-3 text-on-surface">{formatCredits(user.credits)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
