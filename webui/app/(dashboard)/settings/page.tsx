"use client";

import { useEffect, useState } from "react";
import { Save, RefreshCw, Trash2, Plus, ArrowRight, Pencil, List, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { useConfig, useUpdateConfig } from "@/hooks/use-config";
import { useNineRouterModels } from "@/hooks/use-nine-router-models";
import type { ModelOverrideRule, PiiGuardMode, PiiSecretAction } from "@/lib/types";

interface ModelSelectProps {
  value: string;
  onChange: (v: string) => void;
  modelIds: string[];
  placeholder?: string;
  /** When true, the user can switch from the dropdown to a free-text input to type any value. */
  allowFreeText?: boolean;
}

function ModelSelect({ value, onChange, modelIds, placeholder = "Select model...", allowFreeText = false }: ModelSelectProps) {
  const [freeText, setFreeText] = useState(allowFreeText ? !modelIds.includes(value) && value !== "" : false);

  if (allowFreeText && freeText) {
    return (
      <div className="flex items-center gap-1">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="font-mono text-xs h-8 min-w-[200px]"
        />
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          onClick={() => setFreeText(false)}
          title="Switch to dropdown"
        >
          <List className="w-3 h-3" />
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <Select value={value} onValueChange={(v) => onChange(v ?? "auto")}>
        <SelectTrigger className="font-mono text-xs h-8 min-w-[200px]">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="auto">auto</SelectItem>
          {modelIds.map((id) => (
            <SelectItem key={id} value={id}>{id}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {allowFreeText && (
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          onClick={() => setFreeText(true)}
          title="Type a custom value"
        >
          <Pencil className="w-3 h-3" />
        </Button>
      )}
    </div>
  );
}

interface ModelOverrideSectionProps {
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  rules: ModelOverrideRule[];
  onRulesChange: (rules: ModelOverrideRule[]) => void;
  defaultModel: string;
  onDefaultModelChange: (v: string) => void;
  modelIds: string[];
}

function ModelOverrideSection({
  enabled,
  onEnabledChange,
  rules,
  onRulesChange,
  defaultModel,
  onDefaultModelChange,
  modelIds,
}: ModelOverrideSectionProps) {
  function addRule() {
    onRulesChange([...rules, { from: modelIds[0] ?? "auto", to: "auto" }]);
  }

  function updateRule(index: number, field: "from" | "to", value: string) {
    const updated = rules.map((r, i) => (i === index ? { ...r, [field]: value } : r));
    onRulesChange(updated);
  }

  // Normalize a rule's `to` into an array of fallback targets (ordered).
  function targetsOf(rule: ModelOverrideRule): string[] {
    return Array.isArray(rule.to) ? rule.to : [rule.to];
  }

  function setTargets(index: number, targets: string[]) {
    const updated = rules.map((r, i) => (i === index ? { ...r, to: targets.length === 1 ? targets[0] : targets } : r));
    onRulesChange(updated);
  }

  function addTarget(index: number) {
    const targets = targetsOf(rules[index]);
    setTargets(index, [...targets, "auto"]);
  }

  function updateTarget(index: number, targetIndex: number, value: string) {
    const targets = targetsOf(rules[index]);
    const next = targets.map((t, i) => (i === targetIndex ? value : t));
    setTargets(index, next);
  }

  function removeTarget(index: number, targetIndex: number) {
    const targets = targetsOf(rules[index]);
    if (targets.length <= 1) return;
    setTargets(index, targets.filter((_, i) => i !== targetIndex));
  }

  function removeRule(index: number) {
    onRulesChange(rules.filter((_, i) => i !== index));
  }

  return (
    <div className="glass-panel rounded-3xl p-8 md:p-10 group relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-white/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-on-surface">Model Override</h3>
          <p className="text-sm text-on-surface-variant mt-1 max-w-lg">
            Override models on forwarded API requests. Rules are matched by substring (first match
            wins). The default applies when no rule matches. Does not apply to Service Account
            traffic — the model a Service Account is allow-listed for is the model that gets sent
            upstream.
          </p>
        </div>
        <Switch checked={enabled} onCheckedChange={onEnabledChange} />
      </div>

      {enabled && (
        <div className="mt-6 space-y-5">
          {/* Default model */}
          <div className="space-y-2">
            <Label>Default Model</Label>
            <p className="text-xs text-on-surface-variant">Applied when no rule matches the requested model.</p>
            <ModelSelect
              value={defaultModel}
              onChange={onDefaultModelChange}
              modelIds={modelIds}
              placeholder="Select default model..."
            />
          </div>

          {/* Rules table */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Override Rules</Label>
              <Button size="sm" variant="outline" onClick={addRule} className="gap-1 h-7 text-xs">
                <Plus className="w-3 h-3" /> Add Rule
              </Button>
            </div>
            <p className="text-xs text-on-surface-variant">
              First matching rule wins. &quot;From&quot; is matched as a substring of the normalized model name.
              Each rule&apos;s targets are tried in order on failure.
            </p>

            {rules.length === 0 ? (
              <p className="text-sm text-on-surface-variant italic py-3">
                No rules — only the default model applies.
              </p>
            ) : (
              <div className="space-y-2 mt-2">
                {rules.map((rule, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-on-surface-variant w-5 text-right shrink-0">{i + 1}.</span>
                    <ModelSelect
                      value={rule.from}
                      onChange={(v) => updateRule(i, "from", v)}
                      modelIds={modelIds}
                      placeholder="Match model..."
                      allowFreeText
                    />
                    <ArrowRight className="w-4 h-4 text-on-surface-variant shrink-0" />
                    <div className="flex items-center gap-1">
                      {targetsOf(rule).map((target, ti) => (
                        <div key={ti} className="flex items-center gap-1">
                          {ti > 0 && <ArrowRight className="w-3 h-3 text-on-surface-variant/60 shrink-0" />}
                          <ModelSelect
                            value={target}
                            onChange={(v) => updateTarget(i, ti, v)}
                            modelIds={modelIds}
                            placeholder="Replace with..."
                            allowFreeText
                          />
                          {targetsOf(rule).length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeTarget(i, ti)}
                              className="text-on-surface-variant hover:text-error transition-colors p-1 shrink-0"
                              title="Remove fallback target"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      ))}
                      <button
                        type="button"
                        onClick={() => addTarget(i)}
                        className="text-on-surface-variant hover:text-primary transition-colors p-1 shrink-0"
                        title="Add fallback target"
                      >
                        <Plus className="w-3 h-3" />
                      </button>
                    </div>
                    <button
                      onClick={() => removeRule(i)}
                      className="text-on-surface-variant hover:text-error transition-colors p-1 shrink-0"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface PiiGuardSectionProps {
  mode: PiiGuardMode;
  onModeChange: (v: PiiGuardMode) => void;
  secretAction: PiiSecretAction;
  onSecretActionChange: (v: PiiSecretAction) => void;
  restoreToolArgs: boolean;
  onRestoreToolArgsChange: (v: boolean) => void;
}

function PiiGuardSection({
  mode,
  onModeChange,
  secretAction,
  onSecretActionChange,
  restoreToolArgs,
  onRestoreToolArgsChange,
}: PiiGuardSectionProps) {
  const enabled = mode !== "off";

  return (
    <div className="glass-panel rounded-3xl p-8 md:p-10 group relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-white/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-on-surface">PII Guardrail</h3>
          <p className="text-sm text-on-surface-variant mt-1 max-w-lg">
            Replaces personal data (email, phone, ID, card, IP) with placeholders before a request
            leaves the gateway, and puts the real values back in the response. Takes effect
            immediately — no restart. Turn this off first if replies or tool calls start looking
            wrong.
          </p>
        </div>
        <Switch checked={enabled} onCheckedChange={(v) => onModeChange(v ? "tokenize" : "off")} />
      </div>

      {enabled && (
        <div className="mt-6 space-y-5">
          <div className="space-y-2">
            <Label>Mode</Label>
            <p className="text-xs text-on-surface-variant">
              Tokenize replaces values and restores them on the way back, so the user sees the
              original text. Redact strips them permanently — nothing is restored.
            </p>
            <Select value={mode} onValueChange={(v) => onModeChange(v as PiiGuardMode)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tokenize">Tokenize — restore original on response</SelectItem>
                <SelectItem value="redact">Redact — remove permanently</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Credentials in requests</Label>
            <p className="text-xs text-on-surface-variant">
              Block rejects the request with a 400. Use it only if you can live with a false
              positive stopping a request — library source and documentation do contain things that
              look like keys.
            </p>
            <Select
              value={secretAction}
              onValueChange={(v) => onSecretActionChange(v as PiiSecretAction)}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="warn">Warn — log and forward</SelectItem>
                <SelectItem value="block">Block — reject with 400</SelectItem>
                <SelectItem value="off">Off — do not scan</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {mode === "tokenize" && (
            <div className="flex items-start justify-between gap-6 pt-1">
              <div>
                <Label>Restore inside tool arguments</Label>
                <p className="text-xs text-on-surface-variant mt-1 max-w-lg">
                  Without this, a tool runs against the placeholder instead of the real value. Turn
                  it off only if tool calls come back malformed — chat text keeps being restored
                  either way.
                </p>
              </div>
              <Switch checked={restoreToolArgs} onCheckedChange={onRestoreToolArgsChange} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const { data: config, isLoading, refetch } = useConfig();
  const { data: modelsData } = useNineRouterModels();
  const updateConfig = useUpdateConfig();

  const [enableNineRouterModelOverride, setEnableNineRouterModelOverride] = useState(false);
  const [nineRouterOverrideRules, setNineRouterOverrideRules] = useState<ModelOverrideRule[]>([]);
  const [nineRouterDefaultModel, setNineRouterDefaultModel] = useState("auto");
  const [piiGuardMode, setPiiGuardMode] = useState<PiiGuardMode>("off");
  const [piiSecretAction, setPiiSecretAction] = useState<PiiSecretAction>("warn");
  const [piiRestoreToolArgs, setPiiRestoreToolArgs] = useState(true);
  const [dirty, setDirty] = useState(false);

  const modelIds = modelsData?.models ?? [];

  useEffect(() => {
    if (config) {
      setEnableNineRouterModelOverride(config.enable_nine_router_model_override ?? false);
      setNineRouterOverrideRules(config.nine_router_model_override_rules ?? []);
      setNineRouterDefaultModel(config.nine_router_model_override_default ?? "auto");
      setPiiGuardMode(config.pii_guard_mode ?? "off");
      setPiiSecretAction(config.pii_secret_action ?? "warn");
      setPiiRestoreToolArgs(config.pii_restore_tool_args ?? true);
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
      enable_nine_router_model_override: enableNineRouterModelOverride,
      nine_router_model_override_rules: nineRouterOverrideRules,
      nine_router_model_override_default: nineRouterDefaultModel,
      pii_guard_mode: piiGuardMode,
      pii_secret_action: piiSecretAction,
      pii_restore_tool_args: piiRestoreToolArgs,
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

      <ModelOverrideSection
        enabled={enableNineRouterModelOverride}
        onEnabledChange={handleChange(setEnableNineRouterModelOverride)}
        rules={nineRouterOverrideRules}
        onRulesChange={handleChange(setNineRouterOverrideRules)}
        defaultModel={nineRouterDefaultModel}
        onDefaultModelChange={handleChange(setNineRouterDefaultModel)}
        modelIds={modelIds}
      />

      <PiiGuardSection
        mode={piiGuardMode}
        onModeChange={handleChange(setPiiGuardMode)}
        secretAction={piiSecretAction}
        onSecretActionChange={handleChange(setPiiSecretAction)}
        restoreToolArgs={piiRestoreToolArgs}
        onRestoreToolArgsChange={handleChange(setPiiRestoreToolArgs)}
      />

      {updateConfig.isSuccess && !dirty && (
        <div className="glass-panel-elevated rounded-3xl p-4 text-center text-sm text-emerald-700 bg-emerald-50/50">
          Configuration saved and applied successfully. Backend cache has been refreshed.
        </div>
      )}
      {updateConfig.isError && (
        <div className="glass-panel-elevated rounded-3xl p-4 text-center text-sm text-error bg-error/5">
          {(updateConfig.error as any)?.response?.data?.detail || "Failed to save configuration"}
        </div>
      )}
    </div>
  );
}
