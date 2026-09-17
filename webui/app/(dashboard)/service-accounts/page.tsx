"use client";

import { useState } from "react";
import {
  Bot,
  Plus,
  Pencil,
  Trash2,
  KeyRound,
  Copy,
  Check,
  Search,
  X,
  AlertTriangle,
  ShieldAlert,
  BarChart3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  useServiceAccounts,
  useCreateServiceAccount,
  useUpdateServiceAccount,
  useDeleteServiceAccount,
  useServiceAccountKeys,
  useCreateServiceAccountKey,
  useRevokeServiceAccountKey,
  useServiceAccountUsage,
} from "@/hooks/use-service-accounts";
import { useNineRouterModels } from "@/hooks/use-nine-router-models";
import { maskKey, formatCredits, formatDate } from "@/lib/utils";
import type {
  ServiceAccountResponse,
  ServiceAccountKeyCreated,
} from "@/lib/types";

// --- Model Picker ---
// Searchable/filterable multi-select over the live 9router catalog. Fails closed:
// an empty selection is treated as "this account can use NO model" and is called
// out visibly rather than looking like an unrestricted/default state.

function ModelPicker({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (models: string[]) => void;
}) {
  const { data, isLoading, isError } = useNineRouterModels();
  const [query, setQuery] = useState("");

  const catalog = data?.models ?? [];
  const catalogUnavailable = !isLoading && !isError && catalog.length === 0;

  const filtered = catalog.filter((id) =>
    id.toLowerCase().includes(query.trim().toLowerCase())
  );

  function toggle(id: string) {
    if (selected.includes(id)) {
      onChange(selected.filter((m) => m !== id));
    } else {
      onChange([...selected, id]);
    }
  }

  function remove(id: string) {
    onChange(selected.filter((m) => m !== id));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label>Allowed Models</Label>
        {selected.length === 0 ? (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-error">
            <ShieldAlert className="w-3.5 h-3.5" /> No models selected — cannot use ANY model
          </span>
        ) : (
          <span className="text-xs text-on-surface-variant">{selected.length} selected</span>
        )}
      </div>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((id) => (
            <Badge key={id} variant="secondary" className="font-mono gap-1 pr-1">
              {id}
              <button
                type="button"
                onClick={() => remove(id)}
                className="hover:text-error transition-colors rounded-full"
                title={`Remove ${id}`}
              >
                <X className="w-3 h-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      {isLoading ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : isError || catalogUnavailable ? (
        <div className="rounded-xl border border-amber-200/60 bg-amber-50/60 px-4 py-3 text-sm text-on-surface flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold text-amber-900">Model catalog unavailable</p>
            <p className="text-on-surface-variant text-xs mt-0.5">
              9router did not return any models — it may be unreachable or not configured. You
              can&apos;t pick new models right now.
              {selected.length > 0 && " Existing selections above are kept and can still be removed."}
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-outline-variant/50 bg-white/70 overflow-hidden">
          <div className="relative border-b border-outline-variant/30">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-on-surface-variant" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models (e.g. kiro/claude-sonnet-4)..."
              className="w-full pl-9 pr-3 py-2 text-sm bg-transparent outline-none placeholder:text-on-surface-variant/40"
            />
          </div>
          <div className="max-h-52 overflow-y-auto divide-y divide-outline-variant/10">
            {filtered.length === 0 ? (
              <div className="py-6 text-center text-xs text-on-surface-variant">No models match &quot;{query}&quot;</div>
            ) : (
              filtered.map((id) => {
                const isSelected = selected.includes(id);
                return (
                  <button
                    type="button"
                    key={id}
                    onClick={() => toggle(id)}
                    className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs font-mono transition-colors ${
                      isSelected ? "bg-primary/5 text-primary" : "hover:bg-surface-container-lowest text-on-surface"
                    }`}
                  >
                    <span className="truncate">{id}</span>
                    {isSelected && <Check className="w-3.5 h-3.5 shrink-0" />}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// --- Create Dialog ---

function CreateServiceAccountDialog() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const createAccount = useCreateServiceAccount();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || models.length === 0) return;
    await createAccount.mutateAsync({
      name: name.trim(),
      description: description.trim() || undefined,
      allowed_models: models,
    });
    setName("");
    setDescription("");
    setModels([]);
    setOpen(false);
  }

  function handleOpenChange(val: boolean) {
    setOpen(val);
    if (!val) {
      setName("");
      setDescription("");
      setModels([]);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button className="gap-2" />}>
        <Plus className="w-4 h-4" /> New Service Account
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated max-w-lg w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-primary" /> Create Service Account
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="sa-name">Name</Label>
            <Input
              id="sa-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. ci-bot, billing-service"
              required
              minLength={2}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sa-description">Description</Label>
            <Input
              id="sa-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional — what this account is for"
            />
          </div>
          <ModelPicker selected={models} onChange={setModels} />
          <Button type="submit" disabled={createAccount.isPending || !name.trim() || models.length === 0} className="w-full">
            {createAccount.isPending ? "Creating..." : "Create Service Account"}
          </Button>
          {models.length === 0 && (
            <p className="text-xs text-on-surface-variant text-center">
              Select at least one model to enable creation.
            </p>
          )}
          {createAccount.isError && (
            <p className="text-sm text-error">
              {(createAccount.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to create service account"}
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Edit Dialog ---

function EditServiceAccountDialog({ account }: { account: ServiceAccountResponse }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(account.name);
  const [description, setDescription] = useState(account.description ?? "");
  const [models, setModels] = useState<string[]>(account.allowed_models);
  const [isActive, setIsActive] = useState(account.is_active);
  const updateAccount = useUpdateServiceAccount();

  function handleOpenChange(val: boolean) {
    setOpen(val);
    if (val) {
      setName(account.name);
      setDescription(account.description ?? "");
      setModels(account.allowed_models);
      setIsActive(account.is_active);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    await updateAccount.mutateAsync({
      id: account.id,
      data: {
        name: name.trim(),
        description: description.trim() || undefined,
        allowed_models: models,
        is_active: isActive,
      },
    });
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button variant="ghost" size="icon-sm" title="Edit" />}>
        <Pencil className="w-4 h-4" />
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated max-w-lg w-full">
        <DialogHeader>
          <DialogTitle>Edit {account.name}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor={`edit-name-${account.id}`}>Name</Label>
            <Input id={`edit-name-${account.id}`} value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`edit-description-${account.id}`}>Description</Label>
            <Input id={`edit-description-${account.id}`} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Active</Label>
              <p className="text-xs text-on-surface-variant">Inactive accounts cannot authenticate with any key.</p>
            </div>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </div>
          <ModelPicker selected={models} onChange={setModels} />
          {models.length === 0 && (
            <div className="rounded-xl border border-error/30 bg-error/5 px-3 py-2 text-xs text-error flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
              Saving with zero models means this account is locked out of every model — this is
              fail-closed, not "unrestricted".
            </div>
          )}
          <Button type="submit" disabled={updateAccount.isPending || !name.trim()} className="w-full">
            {updateAccount.isPending ? "Saving..." : "Save Changes"}
          </Button>
          {updateAccount.isError && (
            <p className="text-sm text-error">
              {(updateAccount.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to update service account"}
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Keys & Usage Dialog ---

function IssuedKeyBanner({ created }: { created: ServiceAccountKeyCreated }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(created.raw_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3">
      <p className="text-xs font-semibold text-amber-900 flex items-center gap-1.5">
        <AlertTriangle className="w-3.5 h-3.5" /> Copy this key now — it will not be shown again.
      </p>
      <div className="flex items-center gap-2 bg-white rounded-lg px-3 py-2 border border-amber-200/60">
        <code className="flex-1 font-mono text-xs text-on-surface break-all">{created.raw_key}</code>
        <button onClick={handleCopy} className="text-on-surface-variant hover:text-primary transition-colors shrink-0" title="Copy key">
          {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}

function KeysTab({ accountId }: { accountId: number }) {
  const { data: keys, isLoading } = useServiceAccountKeys(accountId);
  const createKey = useCreateServiceAccountKey(accountId);
  const revokeKey = useRevokeServiceAccountKey(accountId);
  const [newKey, setNewKey] = useState<ServiceAccountKeyCreated | null>(null);

  async function handleCreate() {
    const created = await createKey.mutateAsync();
    setNewKey(created);
  }

  async function handleRevoke(keyId: number) {
    if (window.confirm("Revoke this key? Any client using it will immediately lose access.")) {
      await revokeKey.mutateAsync(keyId);
    }
  }

  return (
    <div className="space-y-4">
      <Button onClick={handleCreate} disabled={createKey.isPending} size="sm" className="gap-2">
        <KeyRound className="w-4 h-4" /> {createKey.isPending ? "Issuing..." : "Issue New Key"}
      </Button>

      {newKey && <IssuedKeyBanner created={newKey} />}

      {createKey.isError && (
        <p className="text-xs text-error">
          {(createKey.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to issue key"}
        </p>
      )}

      {isLoading ? (
        <div className="space-y-2">{[1, 2].map((i) => (<Skeleton key={i} className="h-10 rounded-lg" />))}</div>
      ) : keys && keys.length > 0 ? (
        <div className="border border-outline-variant/40 rounded-lg overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-surface-container-low/50">
              <tr>
                <th className="py-2 px-3 font-medium text-on-surface-variant">Key</th>
                <th className="py-2 px-3 font-medium text-on-surface-variant">Created</th>
                <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/20">
              {keys.map((key) => (
                <tr key={key.id} className="hover:bg-surface-container-lowest/50 transition-colors">
                  <td className="py-2 px-3 font-mono text-on-surface-variant">{maskKey(key.key_prefix, key.key_suffix)}</td>
                  <td className="py-2 px-3 text-on-surface-variant">{formatDate(key.created_at)}</td>
                  <td className="py-2 px-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <span className={key.is_active ? "text-emerald-600 font-medium" : "text-on-surface-variant"}>
                        {key.is_active ? "active" : "revoked"}
                      </span>
                      {key.is_active && (
                        <button
                          onClick={() => handleRevoke(key.id)}
                          disabled={revokeKey.isPending}
                          className="text-on-surface-variant hover:text-error transition-colors"
                          title="Revoke key"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-on-surface-variant text-center py-6">No keys issued yet.</p>
      )}
    </div>
  );
}

function UsageTab({ accountId }: { accountId: number }) {
  const [days, setDays] = useState("30");
  const { data: usage, isLoading } = useServiceAccountUsage(accountId, parseInt(days, 10));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <Label className="text-xs text-on-surface-variant">Daily breakdown window</Label>
        <Select value={days} onValueChange={(v) => setDays(v ?? "30")}>
          <SelectTrigger size="sm" className="w-28"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">7 days</SelectItem>
            <SelectItem value="30">30 days</SelectItem>
            <SelectItem value="90">90 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => (<Skeleton key={i} className="h-8 rounded-lg" />))}</div>
      ) : (
        <>
          <div>
            <h4 className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Monthly Rollup</h4>
            {usage && usage.monthly.length > 0 ? (
              <div className="border border-outline-variant/40 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-container-low/50">
                    <tr>
                      <th className="py-2 px-3 font-medium text-on-surface-variant">Month</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Usage</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Last Used</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/20">
                    {usage.monthly.map((m) => (
                      <tr key={m.month}>
                        <td className="py-2 px-3 font-mono">{m.month}</td>
                        <td className="py-2 px-3 text-right font-mono">{formatCredits(m.current_usage)}</td>
                        <td className="py-2 px-3 text-right text-on-surface-variant">
                          {m.last_used_at ? formatDate(m.last_used_at) : "never"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-on-surface-variant py-3">No usage recorded yet.</p>
            )}
          </div>

          <div>
            <h4 className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Daily Breakdown by Model</h4>
            {usage && usage.daily.length > 0 ? (
              <div className="border border-outline-variant/40 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-surface-container-low/50 sticky top-0">
                    <tr>
                      <th className="py-2 px-3 font-medium text-on-surface-variant">Date</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant">Model</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Input</th>
                      <th className="py-2 px-3 font-medium text-on-surface-variant text-right">Output</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/20">
                    {usage.daily.map((d, i) => (
                      <tr key={`${d.date}-${d.model}-${i}`}>
                        <td className="py-2 px-3">{d.date}</td>
                        <td className="py-2 px-3 font-mono">{d.model}</td>
                        <td className="py-2 px-3 text-right font-mono">{formatCredits(d.input_tokens)}</td>
                        <td className="py-2 px-3 text-right font-mono">{formatCredits(d.output_tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-on-surface-variant py-3">No daily usage in this window.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ManageServiceAccountDialog({ account }: { account: ServiceAccountResponse }) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="ghost" size="icon-sm" title="Manage keys & usage" />}>
        <KeyRound className="w-4 h-4" />
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated max-w-xl w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-primary" /> {account.name}
          </DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="keys" className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="keys" className="flex-1 gap-1.5"><KeyRound className="w-3.5 h-3.5" /> Keys</TabsTrigger>
            <TabsTrigger value="usage" className="flex-1 gap-1.5"><BarChart3 className="w-3.5 h-3.5" /> Usage</TabsTrigger>
          </TabsList>
          <TabsContent value="keys" className="mt-4">
            {open && <KeysTab accountId={account.id} />}
          </TabsContent>
          <TabsContent value="usage" className="mt-4">
            {open && <UsageTab accountId={account.id} />}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

// --- Row & Table ---

function ServiceAccountRow({ account }: { account: ServiceAccountResponse }) {
  const updateAccount = useUpdateServiceAccount();
  const deleteAccount = useDeleteServiceAccount();
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleDelete() {
    if (window.confirm(`Delete service account "${account.name}"? All of its keys will stop working immediately. This cannot be undone.`)) {
      setIsDeleting(true);
      try {
        await deleteAccount.mutateAsync(account.id);
      } finally {
        setIsDeleting(false);
      }
    }
  }

  return (
    <tr className="hover:bg-surface-container-lowest transition-colors">
      <td className="py-4 px-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant shrink-0 border border-outline-variant/30">
            <Bot className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="font-medium text-on-surface truncate">{account.name}</div>
            {account.description && (
              <div className="text-on-surface-variant text-xs mt-0.5 truncate max-w-xs">{account.description}</div>
            )}
          </div>
        </div>
      </td>
      <td className="py-4 px-6 font-mono text-sm">{account.key_count}</td>
      <td className="py-4 px-6">
        {account.allowed_model_count === 0 ? (
          <Badge variant="destructive" className="gap-1"><ShieldAlert className="w-3 h-3" /> 0 models</Badge>
        ) : (
          <span className="font-mono text-sm">{account.allowed_model_count}</span>
        )}
      </td>
      <td className="py-4 px-6">
        <Switch
          checked={account.is_active}
          onCheckedChange={(checked) => updateAccount.mutate({ id: account.id, data: { is_active: checked } })}
          disabled={updateAccount.isPending}
        />
      </td>
      <td className="py-4 px-6 text-on-surface-variant text-xs">{formatDate(account.created_at)}</td>
      <td className="py-4 px-6 text-right">
        <div className="flex items-center justify-end gap-1">
          <ManageServiceAccountDialog account={account} />
          <EditServiceAccountDialog account={account} />
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={handleDelete}
            disabled={isDeleting || deleteAccount.isPending}
            title="Delete"
            className="hover:text-error"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      </td>
    </tr>
  );
}

// --- Main Page ---

export default function ServiceAccountsPage() {
  const { data: accounts, isLoading } = useServiceAccounts();

  const total = accounts?.length ?? 0;
  const active = accounts?.filter((a) => a.is_active).length ?? 0;
  const totalKeys = accounts?.reduce((sum, a) => sum + a.key_count, 0) ?? 0;
  const zeroModelAccounts = accounts?.filter((a) => a.allowed_model_count === 0).length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-on-surface">Service Accounts</h1>
          <p className="text-on-surface-variant text-sm mt-0.5">
            Non-human identities (CI bots, apps, teams) with their own API keys and model allowlist.
          </p>
        </div>
        <CreateServiceAccountDialog />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-bento-gap">
        <div className="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] backdrop-blur-[20px] bg-white/80">
          <div className="flex justify-between items-start mb-2">
            <span className="text-label-caps font-label-caps text-on-surface-variant uppercase tracking-wider">Service Accounts</span>
            <Bot className="text-outline w-5 h-5" />
          </div>
          <div className="text-4xl font-display text-on-surface tracking-tight font-mono">{total}</div>
          <div className="text-xs text-on-surface-variant mt-1">{active} active</div>
        </div>
        <div className="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] relative overflow-hidden backdrop-blur-[20px] bg-white/80">
          <div className="absolute top-0 right-0 w-32 h-32 bg-sky-100 rounded-full blur-3xl opacity-50 -mr-10 -mt-10 pointer-events-none" />
          <div className="flex justify-between items-start mb-2 relative z-10">
            <span className="text-label-caps font-label-caps text-on-surface-variant uppercase tracking-wider">Keys Issued</span>
            <KeyRound className="text-sky-600 w-5 h-5" />
          </div>
          <div className="text-4xl font-display text-on-surface tracking-tight font-mono relative z-10">{totalKeys}</div>
          <div className="text-xs text-on-surface-variant mt-1 relative z-10">across all accounts</div>
        </div>
        <div className="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] backdrop-blur-[20px] bg-white/80">
          <div className="flex justify-between items-start mb-2">
            <span className="text-label-caps font-label-caps text-on-surface-variant uppercase tracking-wider">Locked Out</span>
            <ShieldAlert className={`w-5 h-5 ${zeroModelAccounts > 0 ? "text-error" : "text-outline"}`} />
          </div>
          <div className={`text-4xl font-display tracking-tight font-mono ${zeroModelAccounts > 0 ? "text-error" : "text-on-surface"}`}>{zeroModelAccounts}</div>
          <div className="text-xs text-on-surface-variant mt-1">accounts with 0 allowed models</div>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">{[1, 2, 3].map((i) => (<Skeleton key={i} className="h-16 rounded-xl" />))}</div>
      ) : (
        <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-low/50 border-b border-outline-variant/30">
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Name</th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Keys</th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Allowed Models</th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Active</th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Created</th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="text-body-sm divide-y divide-outline-variant/20">
              {(accounts || []).map((a) => (<ServiceAccountRow key={a.id} account={a} />))}
            </tbody>
          </table>
          {(!accounts || accounts.length === 0) && (
            <div className="p-8 text-center text-on-surface-variant">
              No service accounts yet. Create one to issue API keys to a CI bot, app, or team.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
