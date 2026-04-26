"use client";

import { useEffect, useState } from "react";
import { Save, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig, useUpdateConfig } from "@/hooks/use-config";

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
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-h1 font-bold text-on-surface tracking-tight">
            Gateway Configuration
          </h1>
          <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">
            Configure dynamic gateway parameters. Changes apply immediately
            without server restart.
          </p>
        </div>
        <div className="flex gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            className="gap-2"
          >
            <RefreshCw className="w-4 h-4" /> Reload
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!dirty || updateConfig.isPending}
            className="gap-2"
          >
            <Save className="w-4 h-4" />
            {updateConfig.isPending ? "Saving..." : "Apply Changes"}
          </Button>
        </div>
      </div>

      {/* Model Override Section */}
      <div className="glass-panel rounded-2xl p-8">
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
      <div className="glass-panel rounded-2xl p-8">
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

      {/* Save confirmation */}
      {updateConfig.isSuccess && !dirty && (
        <div className="glass-panel-elevated rounded-2xl p-4 text-center text-sm text-emerald-700 bg-emerald-50/50">
          Configuration saved and applied successfully. Backend cache has been
          refreshed.
        </div>
      )}
      {updateConfig.isError && (
        <div className="glass-panel-elevated rounded-2xl p-4 text-center text-sm text-error bg-error/5">
          {(updateConfig.error as any)?.response?.data?.detail ||
            "Failed to save configuration"}
        </div>
      )}
    </div>
  );
}
