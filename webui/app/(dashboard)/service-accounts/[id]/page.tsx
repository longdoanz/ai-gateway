"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Bot } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useServiceAccounts, useUpdateServiceAccount } from "@/hooks/use-service-accounts";
import { AllowedModelsBadges } from "@/components/service-accounts/allowed-models";
import { UsagePanel } from "@/components/service-accounts/usage-panel";
import { formatDate } from "@/lib/utils";

export default function ServiceAccountDetailPage() {
  const params = useParams<{ id: string }>();
  const accountId = parseInt(params.id, 10);
  const { data: accounts, isLoading } = useServiceAccounts();
  const updateAccount = useUpdateServiceAccount();

  const account = accounts?.find((a) => a.id === accountId);

  return (
    <div className="space-y-6">
      <Link
        href="/service-accounts"
        className="inline-flex items-center gap-1.5 text-sm text-on-surface-variant hover:text-primary transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back to Service Accounts
      </Link>

      {isLoading ? (
        <>
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
        </>
      ) : !account ? (
        <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl p-8 text-center text-on-surface-variant">
          Service account not found. It may have been deleted.
        </div>
      ) : (
        <>
          <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] p-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant shrink-0 border border-outline-variant/30">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <h1 className="text-xl font-black tracking-tight text-on-surface">{account.name}</h1>
                  {account.description && (
                    <p className="text-on-surface-variant text-sm mt-0.5">{account.description}</p>
                  )}
                  <p className="text-xs text-on-surface-variant mt-1">
                    Created {formatDate(account.created_at)} &middot; {account.key_count} key
                    {account.key_count === 1 ? "" : "s"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-on-surface-variant">Active</span>
                <Switch
                  checked={account.is_active}
                  onCheckedChange={(checked) => updateAccount.mutate({ id: account.id, data: { is_active: checked } })}
                  disabled={updateAccount.isPending}
                />
              </div>
            </div>

            <div className="mt-4">
              <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1.5">
                Allowed Models
              </p>
              <AllowedModelsBadges models={account.allowed_models} max={Infinity} />
            </div>
          </div>

          <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] p-6">
            <h2 className="text-sm font-semibold text-on-surface mb-4">Usage</h2>
            <UsagePanel accountId={account.id} />
          </div>
        </>
      )}
    </div>
  );
}
