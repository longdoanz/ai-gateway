"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, BarChart3, UserCog, Settings, LogOut, ChevronUp, Copy, Check, KeyRound, Trash2, ExternalLink } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { useGatewayKey, useCreateGatewayKey, useRevokeGatewayKey } from "@/hooks/use-gateway-keys";
import { cn } from "@/lib/utils";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { maskKey } from "@/lib/utils";
import type { GatewayKeyCreated } from "@/lib/types";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, adminOnly: false },
  { href: "/analytics", label: "Analytics", icon: BarChart3, adminOnly: false },
  { href: "/accounts", label: "Accounts", icon: UserCog, adminOnly: true },
  { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

const NINE_ROUTER_ENABLED = process.env.NEXT_PUBLIC_NINE_ROUTER_ENABLED === "true";

function NineRouterButton() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);

  if (!NINE_ROUTER_ENABLED || user?.role !== "admin") return null;

  async function handleClick() {
    setLoading(true);
    try {
      // Build OIDC authorization URL with prompt=none and current JWT
      const accessToken = localStorage.getItem("access_token") || sessionStorage.getItem("access_token") || "";
      const redirectUri = encodeURIComponent(`${window.location.origin}/9router/api/auth/oidc/callback`);
      const state = crypto.randomUUID();
      const nonce = crypto.randomUUID();

      // Generate PKCE pair
      const verifierBytes = crypto.getRandomValues(new Uint8Array(32));
      const verifier = btoa(String.fromCharCode(...verifierBytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
      const challengeBytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
      const challenge = btoa(String.fromCharCode(...new Uint8Array(challengeBytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");

      // Store PKCE verifier for 9router to pick up (9router uses cookies, but since we control
      // the redirect we use the gateway proxy path which shares the same origin)
      sessionStorage.setItem("oidc_pkce_verifier", verifier);

      const params = new URLSearchParams({
        client_id: "9router",
        redirect_uri: `${window.location.origin}/9router/api/auth/oidc/callback`,
        response_type: "code",
        scope: "openid profile email",
        state,
        nonce,
        code_challenge: challenge,
        code_challenge_method: "S256",
        prompt: "none",
        _gateway_token: accessToken,
      });

      window.open(`/api/oauth/authorize?${params}`, "_blank", "noopener");
    } catch {
      // Fallback: open 9router directly (user will see its own login)
      window.open("/9router/", "_blank", "noopener");
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className="flex items-center gap-3 w-full px-4 py-3 rounded-xl transition-all duration-200 font-medium text-on-surface-variant hover:bg-white/60 hover:text-primary hover:-translate-y-[1px] active:scale-95 disabled:opacity-60"
    >
      <ExternalLink className="w-5 h-5" />
      <span>{loading ? "Opening..." : "9Router Admin"}</span>
    </button>
  );
}


function GatewayKeyDialog() {
  const { user } = useAuth();
  const { data: gatewayKey, isLoading } = useGatewayKey();
  const createKey = useCreateGatewayKey();
  const revokeKey = useRevokeGatewayKey();
  const [newKey, setNewKey] = useState<GatewayKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(false);
  const { logout } = useAuth();

  if (!user) return null;

  async function handleCreate() {
    const created = await createKey.mutateAsync();
    setNewKey(created);
  }

  async function handleRevoke() {
    await revokeKey.mutateAsync();
    setNewKey(null);
  }

  function handleCopy(key: string) {
    navigator.clipboard.writeText(key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleOpenChange(val: boolean) {
    setOpen(val);
    if (!val) setNewKey(null);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={
        <button className="flex items-center gap-3 w-full p-2 rounded-xl hover:bg-surface-container-low transition-colors text-left">
          <div className="w-10 h-10 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30 ring-2 ring-surface-container">
            {(user.username || user.role).slice(0, 2).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-on-surface truncate">{user.username || (user.role === "admin" ? "Admin" : "User")}</p>
            <p className="text-xs text-on-surface-variant truncate capitalize">{user.role}</p>
          </div>
          <ChevronUp className="w-4 h-4 text-on-surface-variant" />
        </button>
      } />
      <DialogContent className="glass-panel-elevated max-w-lg w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">
              {(user.username || user.role).slice(0, 2).toUpperCase()}
            </div>
            {user.username}
          </DialogTitle>
        </DialogHeader>

        {(user.can_create_gateway_key || gatewayKey) && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-on-surface">
              <KeyRound className="w-4 h-4 text-primary" />
              Gateway Key
            </div>

            {isLoading ? (
              <div className="h-10 bg-surface-container animate-pulse rounded-lg" />
            ) : newKey ? (
              <div className="space-y-2">
                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  Copy this key now — it won&apos;t be shown again.
                </p>
                <div className="flex items-center gap-2 bg-surface-container rounded-lg px-3 py-2">
                  <code className="flex-1 font-mono text-xs text-on-surface break-all">{newKey.raw_key}</code>
                  <button onClick={() => handleCopy(newKey.raw_key)} className="text-on-surface-variant hover:text-primary transition-colors shrink-0">
                    {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            ) : gatewayKey ? (
              <div className="flex items-center justify-between bg-surface-container rounded-lg px-3 py-2">
                <code className="font-mono text-xs text-on-surface">{maskKey(gatewayKey.key_prefix, gatewayKey.key_suffix)}</code>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-emerald-600 font-medium">active</span>
                  <button
                    onClick={handleRevoke}
                    disabled={revokeKey.isPending}
                    className="text-on-surface-variant hover:text-error transition-colors"
                    title="Revoke key"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ) : user.can_create_gateway_key ? (
              <Button onClick={handleCreate} disabled={createKey.isPending} size="sm" className="w-full gap-2">
                <KeyRound className="w-4 h-4" />
                {createKey.isPending ? "Creating..." : "Create Gateway Key"}
              </Button>
            ) : (
              <p className="text-xs text-on-surface-variant bg-surface-container rounded-lg px-3 py-2">
                Contact an admin to enable gateway key access.
              </p>
            )}

            {createKey.isError && (
              <p className="text-xs text-error">{(createKey.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to create key"}</p>
            )}

            <div className="border-t border-outline-variant/30 pt-3" />
          </div>
        )}

        <button
          onClick={() => { logout(); setOpen(false); }}
          className="flex items-center justify-between w-full px-3 py-2 text-sm text-error hover:bg-error/5 rounded-lg transition-colors"
        >
          <span className="font-medium">Logout</span>
          <LogOut className="w-4 h-4" />
        </button>
      </DialogContent>
    </Dialog>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const visibleItems = navItems.filter(
    (item) => !item.adminOnly || user?.role === "admin"
  );

  return (
    <nav className="hidden md:flex flex-col fixed left-0 top-0 h-screen w-64 border-r border-slate-200/50 bg-white/60 backdrop-blur-xl shadow-[0_0_30px_rgba(0,0,0,0.02)] z-40">
      <div className="p-6 mb-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary-container to-primary flex items-center justify-center text-white font-bold shadow-sm">
            AI
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-on-surface">AI Gateway</h1>
            <p className="text-xs text-on-surface-variant font-medium">AI Usage Management</p>
          </div>
        </div>
      </div>

      <div className="flex-1 px-4 space-y-1">
        {visibleItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 font-medium",
                isActive
                  ? "text-primary bg-primary/5 shadow-sm border border-primary/10 font-semibold"
                  : "text-on-surface-variant hover:bg-white/60 hover:text-primary hover:-translate-y-[1px] active:scale-95"
              )}
            >
              <item.icon className="w-5 h-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
        <NineRouterButton />
      </div>

      <div className="p-4 mt-auto space-y-1 border-t border-slate-200/50">
        {user && <GatewayKeyDialog />}
      </div>
    </nav>
  );
}
