"use client";

import { useState } from "react";
import { ChevronRight, ChevronDown, Plus, Key } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useKeys, useCreateKey, useToggleKey } from "@/hooks/use-keys";
import { useUsers } from "@/hooks/use-users";
import { useAuth } from "@/hooks/use-auth";
import { maskKey, formatCredits } from "@/lib/utils";
import { BarChartUsers } from "@/components/charts/bar-chart-users";
import type { ApiKeyResponse, UserResponse } from "@/lib/types";

function AddKeyDialog() {
  const [rawKey, setRawKey] = useState("");
  const [open, setOpen] = useState(false);
  const createKey = useCreateKey();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await createKey.mutateAsync({ raw_key: rawKey });
    setRawKey("");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" className="gap-2" />}>
        <Plus className="w-4 h-4" /> Register Key
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated">
        <DialogHeader>
          <DialogTitle>Register API Key</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="raw_key">Kiro API Key</Label>
            <Input id="raw_key" value={rawKey} onChange={(e) => setRawKey(e.target.value)} placeholder="sk-proj-..." className="font-mono text-sm" required minLength={10} />
            <p className="text-xs text-on-surface-variant">The key will be encrypted. Only prefix and suffix are stored visibly.</p>
          </div>
          <Button type="submit" disabled={createKey.isPending} className="w-full">
            {createKey.isPending ? "Registering..." : "Register Key"}
          </Button>
          {createKey.isError && (
            <p className="text-sm text-error">{(createKey.error as any)?.response?.data?.detail || "Failed to register key"}</p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

function KeyRow({ apiKey }: { apiKey: ApiKeyResponse }) {
  const toggleKey = useToggleKey();
  return (
    <tr className="border-b border-outline-variant/20">
      <td className="py-3 px-4 text-on-surface font-medium text-xs">{apiKey.kiro_user_id || "—"}</td>
      <td className="py-3 px-4 font-mono text-on-surface-variant text-xs">{maskKey(apiKey.key_prefix, apiKey.key_suffix)}</td>
      <td className="py-3 px-4 text-on-surface-variant text-xs">{new Date(apiKey.created_at).toLocaleDateString()}</td>
      <td className="py-3 px-4 text-right">
        <Switch checked={apiKey.is_active} onCheckedChange={(checked) => toggleKey.mutate({ keyId: apiKey.id, isActive: checked })} disabled={toggleKey.isPending} />
      </td>
    </tr>
  );
}

function UserRow({ user, keys, isExpanded, onToggle }: { user: UserResponse; keys: ApiKeyResponse[]; isExpanded: boolean; onToggle: () => void }) {
  const userKeys = keys.filter((k) => k.user_id === user.id);
  return (
    <>
      <tr className={`hover:bg-surface-container-lowest transition-colors cursor-pointer group ${isExpanded ? "bg-sky-50/30" : ""}`} onClick={onToggle}>
        <td className="py-4 px-6 text-center">
          <button className="text-outline group-hover:text-primary hover:bg-surface-container rounded-full p-0.5 transition-colors">
            {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
          </button>
        </td>
        <td className="py-4 px-6">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">{user.username.slice(0, 2).toUpperCase()}</div>
            <div><div className="font-medium text-on-surface">{user.username}</div></div>
          </div>
        </td>
        <td className="py-4 px-6"><Badge variant={user.role === "admin" ? "default" : "secondary"} className="text-[10px]">{user.role}</Badge></td>
        <td className="py-4 px-6">
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${user.is_active ? "bg-emerald-100/50 text-emerald-800 border-emerald-200/50" : "bg-surface-variant text-on-surface-variant border-outline-variant/50"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${user.is_active ? "bg-emerald-500" : "bg-outline"}`} />
            {user.is_active ? "Active" : "Inactive"}
          </span>
        </td>
        <td className="py-4 px-6 text-right font-mono text-sm">{userKeys.length}</td>
      </tr>
      {isExpanded && (
        <tr className="bg-surface-container-lowest border-b-2 border-primary/10">
          <td colSpan={5} className="p-0">
            <div className="px-12 py-6 pl-20 bg-gradient-to-b from-sky-50/20 to-transparent">
              <div className="flex justify-between items-center mb-4">
                <h4 className="font-mono text-mono-label text-on-surface font-semibold flex items-center gap-2"><Key className="w-4 h-4 text-sky-600" /> API Keys ({userKeys.length})</h4>
              </div>
              {userKeys.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No API keys registered.</p>
              ) : (
                <div className="border border-outline-variant/40 rounded-lg overflow-hidden bg-white">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-surface-container-low/50">
                      <tr>
                        <th className="py-2 px-4 font-medium text-on-surface-variant">Kiro User ID</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant font-mono">Token Secret</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant">Created</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-outline-variant/20">
                      {userKeys.map((key) => (<KeyRow key={key.id} apiKey={key} />))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function UsersPage() {
  const { user: authUser } = useAuth();
  const { data: users, isLoading: usersLoading } = useUsers();
  const { data: keys, isLoading: keysLoading } = useKeys();
  const [expandedUserId, setExpandedUserId] = useState<number | null>(null);
  const isLoading = usersLoading || keysLoading;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-h1 font-bold text-on-surface tracking-tight">User & Tokens</h1>
          <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">Manage users, their access roles, and API key registration.</p>
        </div>
        <AddKeyDialog />
      </div>
      <Tabs defaultValue="access" className="w-full">
        <TabsList>
          <TabsTrigger value="access">Access & Overrides</TabsTrigger>
          <TabsTrigger value="analytics">Usage Analytics</TabsTrigger>
        </TabsList>
        <TabsContent value="access" className="mt-6">
          {isLoading ? (
            <div className="space-y-3">{[1, 2, 3].map((i) => (<Skeleton key={i} className="h-16 rounded-xl" />))}</div>
          ) : (
            <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-surface-container-low/50 border-b border-outline-variant/30">
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider w-12" />
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">User Details</th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Role</th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Status</th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider text-right">Keys</th>
                  </tr>
                </thead>
                <tbody className="text-body-sm divide-y divide-outline-variant/20">
                  {(users || []).map((u) => (
                    <UserRow key={u.id} user={u} keys={keys || []} isExpanded={expandedUserId === u.id} onToggle={() => setExpandedUserId(expandedUserId === u.id ? null : u.id)} />
                  ))}
                </tbody>
              </table>
              {(!users || users.length === 0) && (<div className="p-8 text-center text-on-surface-variant">No users found.</div>)}
            </div>
          )}
        </TabsContent>
        <TabsContent value="analytics" className="mt-6">
          <div className="glass-panel rounded-2xl p-6 h-[400px]">
            <h3 className="text-lg font-semibold text-on-surface mb-4">User Credit Consumption</h3>
            <div className="h-[320px]"><BarChartUsers users={users || []} keys={keys || []} /></div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
