"use client";

import { useEffect, useState } from "react";
import { Save, RefreshCw, Trash2, Plus, Key } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useConfig, useUpdateConfig } from "@/hooks/use-config";
import { useSystemKeys, useCreateSystemKey, useUpdateSystemKey, useDeleteSystemKey } from "@/hooks/use-system-keys";
import { maskKey } from "@/lib/utils";

function AddSystemKeyDialog() {
  const [rawKey, setRawKey] = useState("");
  const [useProxy, setUseProxy] = useState(false);
  const [open, setOpen] = useState(false);
  const createKey = useCreateSystemKey();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await createKey.mutateAsync({
      raw_key: rawKey,
      use_proxy: useProxy,
    });
    setRawKey("");
    setUseProxy(false);
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="w-4 h-4" /> Add Kiro Key
        </Button>
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated max-w-md w-full">
        <DialogHeader>
          <DialogTitle>Register System API Key</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-4">
          <div className="space-y-2">
            <Label htmlFor="raw_key">Kiro API Key</Label>
            <Input
              id="raw_key"
              value={rawKey}
              onChange={(e) => setRawKey(e.target.value)}
              placeholder="sk-proj-..."
              className="font-mono text-sm"
              required
              minLength={10}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Use Proxy</Label>
              <p className="text-xs text-on-surface-variant">Enable if this key requires a proxy</p>
            </div>
            <Switch checked={useProxy} onCheckedChange={setUseProxy} />
          </div>
          <Button type="submit" disabled={createKey.isPending} className="w-full">
            {createKey.isPending ? "Registering..." : "Register Key"}
          </Button>
          {createKey.isError && (
            <p className="text-sm text-error">
              {(createKey.error as any)?.response?.data?.detail || "Failed to register key"}
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SystemKeysSection() {
  const { data: keys, isLoading } = useSystemKeys();
  const updateKey = useUpdateSystemKey();
  const deleteKey = useDeleteSystemKey();

  if (isLoading) {
    return <Skeleton className="h-48 rounded-3xl" />;
  }

  return (
    <div className="glass-panel rounded-3xl p-8 md:p-10 group relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-white/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-on-surface flex items-center gap-2">
            <Key className="w-5 h-5 text-sky-600" />
            System Kiro Keys
          </h3>
          <p className="text-sm text-on-surface-variant mt-1">
            Manage system-level backup keys used for the fallback mechanism.
          </p>
        </div>
        <AddSystemKeyDialog />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-outline-variant/30">
              <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Key</th>
              <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider text-center">Proxy</th>
              <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider text-center">Status</th>
              <th className="py-3 px-4 text-right"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/20">
            {keys?.map((key) => (
              <tr key={key.id} className="hover:bg-surface-container-lowest/50 transition-colors">
                <td className="py-3 px-4 font-mono text-xs text-on-surface">
                  {maskKey(key.key_prefix, key.key_suffix)}
                </td>
                <td className="py-3 px-4 text-center">
                  <Switch
                    checked={key.use_proxy}
                    onCheckedChange={(checked) =>
                      updateKey.mutate({ keyId: key.id, data: { use_proxy: checked } })
                    }
                    disabled={updateKey.isPending}
                    className="scale-75"
                  />
                </td>
                <td className="py-3 px-4 text-center">
                  <Switch
                    checked={key.is_active}
                    onCheckedChange={(checked) =>
                      updateKey.mutate({ keyId: key.id, data: { is_active: checked } })
                    }
                    disabled={updateKey.isPending}
                    className="scale-75"
                  />
                </td>
                <td className="py-3 px-4 text-right">
                  <button
                    onClick={() => {
                      if (confirm("Are you sure you want to delete this system key?")) {
                        deleteKey.mutate(key.id);
                      }
                    }}
                    disabled={deleteKey.isPending}
                    className="text-on-surface-variant hover:text-error transition-colors p-1"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
            {keys?.length === 0 && (
              <tr>
                <td colSpan={4} className="py-8 text-center text-sm text-on-surface-variant italic">
                  No system keys registered yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { data: config, isLoading, refetch } = useConfig();
  const updateConfig = useUpdateConfig();

  const [enableModelOverride, setEnableModelOverride] = useState(false);
  const [enforcedModel, setEnforcedModel] = useState("auto");
  const [enableUsageSharing, setEnableUsageSharing] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (config) {
      setEnableModelOverride(config.enable_model_override);
      setEnforcedModel(config.enforced_global_model);
      setEnableUsageSharing(config.enable_usage_sharing);
      setDirty(false);
    }
  }, [config]);

  function handleChange<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setDirty(true);
    };
  }

  async function handleSave() {
    await updateConfig.mutateAsync({
      enable_model_override: enableModelOverride,
      enforced_global_model: enforcedModel,
      enable_usage_sharing: enableUsageSharing,
    });
    setDirty(false);
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-32 rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex justify-end">
        <div className="flex gap-3">
          <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-2">
            <RefreshCw className="w-4 h-4" /> Reload
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!dirty || updateConfig.isPending} className="gap-2">
            <Save className="w-4 h-4" />
            {updateConfig.isPending ? "Saving..." : "Apply Changes"}
          </Button>
        </div>
      </div>

      {/* Model Override Section */}
      <div className="glass-panel rounded-3xl p-8 md:p-10 group relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-white/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-on-surface">
              Global Model Enforcement
            </h3>
            <p className="text-sm text-on-surface-variant mt-1 max-w-lg">
              When enabled, all API requests will be forced to use the specified
              model, regardless of what the client requests.
            </p>
          </div>
          <Switch
            checked={enableModelOverride}
            onCheckedChange={handleChange(setEnableModelOverride)}
          />
        </div>
        {enableModelOverride && (
          <div className="mt-6 space-y-2">
            <Label htmlFor="enforced-model">Enforced Model</Label>
            <Input
              id="enforced-model"
              value={enforcedModel}
              onChange={(e) =>
                handleChange(setEnforcedModel)(e.target.value)
              }
              placeholder="e.g. auto, claude-haiku-4.5, claude-sonnet-4.6"
              className="max-w-md font-mono text-sm"
            />
            <p className="text-xs text-on-surface-variant">
              Use &quot;auto&quot; for automatic model selection, or specify an
              exact model ID.
            </p>
          </div>
        )}
      </div>

      {/* Usage Sharing / Fallback Section */}
      <div className="glass-panel rounded-3xl p-8 md:p-10 group relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-white/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-on-surface">
              Usage Sharing (Fallback)
            </h3>
            <p className="text-sm text-on-surface-variant mt-1 max-w-lg">
              When enabled, the gateway will automatically use round-robin
              fallback to borrow a backup key when the primary key is below 1%
              of its usage limit.
            </p>
          </div>
          <Switch
            checked={enableUsageSharing}
            onCheckedChange={handleChange(setEnableUsageSharing)}
          />
        </div>
      </div>

      {/* System Keys Section */}
      <SystemKeysSection />

      {/* Save confirmation */}
      {updateConfig.isSuccess && !dirty && (
        <div className="glass-panel-elevated rounded-3xl p-4 text-center text-sm text-emerald-700 bg-emerald-50/50">
          Configuration saved and applied successfully. Backend cache has been
          refreshed.
        </div>
      )}
      {updateConfig.isError && (
        <div className="glass-panel-elevated rounded-3xl p-4 text-center text-sm text-error bg-error/5">
          {(updateConfig.error as any)?.response?.data?.detail ||
            "Failed to save configuration"}
        </div>
      )}
    </div>
  );
}
