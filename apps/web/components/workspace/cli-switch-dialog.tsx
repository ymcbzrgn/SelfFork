/**
 * CLI switch / routing control for a workspace.
 *
 * Opened from the Live Run Theater's "Switch CLI" button. Surfaces the
 * same /api/router/* state Self Jr's router tools mutate, so the operator
 * can steer routing by hand:
 *   - force a CLI (+ optional model) for THIS workspace (sticky override),
 *   - see the affinity candidates the router would otherwise pick,
 *   - tune a CLI's effort and enabled-model set (these apply everywhere).
 *
 * No hardcoded model/effort lists — every menu sources from /capabilities
 * (project_ui_stack.md: the backend is the single source of truth). Writes
 * affect the NEXT selection, not the run already on screen (ADR-006 §4.6).
 */
"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  ApiError,
  clearRouterOverride,
  getCliConfig,
  getRouterAffinity,
  listCliCapabilities,
  putCliEffort,
  putCliEnabledModels,
  setRouterOverride,
  type CliCapability,
  type CliRuntimeConfig,
  type RouterAffinityView,
} from "@/lib/api";

// Radix Select forbids an empty-string item value, so the "use the CLI's
// own default" choice rides a sentinel that maps back to null on write.
const DEFAULT_SENTINEL = "__default__";

function errMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

export interface CliSwitchDialogProps {
  slug: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CliSwitchDialog({
  slug,
  open,
  onOpenChange,
}: CliSwitchDialogProps) {
  const [caps, setCaps] = useState<CliCapability[] | null>(null);
  const [affinity, setAffinity] = useState<RouterAffinityView | null>(null);
  const [config, setConfig] = useState<CliRuntimeConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCli, setSelectedCli] = useState("");
  const [selectedModel, setSelectedModel] = useState(DEFAULT_SENTINEL);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError(null);
    Promise.all([
      listCliCapabilities(),
      getRouterAffinity(slug),
      getCliConfig(),
    ])
      .then(([c, a, cfg]) => {
        if (cancelled) return;
        setCaps(c);
        setAffinity(a);
        setConfig(cfg);
        const initialCli = a.active_override?.cli ?? c[0]?.cli ?? "";
        setSelectedCli(initialCli);
        setSelectedModel(
          a.active_override?.cli === initialCli && a.active_override.model
            ? a.active_override.model
            : DEFAULT_SENTINEL,
        );
      })
      .catch((e) => {
        if (!cancelled) setError(errMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open, slug]);

  const refreshDynamic = async () => {
    const [a, cfg] = await Promise.all([
      getRouterAffinity(slug),
      getCliConfig(),
    ]);
    setAffinity(a);
    setConfig(cfg);
  };

  // Every write shares the same busy/error/refresh envelope.
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refreshDynamic();
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const selectedCap = caps?.find((c) => c.cli === selectedCli) ?? null;
  const enabledModels =
    config?.enabled_models?.[selectedCli] ?? selectedCap?.models ?? [];
  const persistedEffort = config?.efforts?.[selectedCli];
  const currentEffort =
    persistedEffort && selectedCap?.effort_levels.includes(persistedEffort)
      ? persistedEffort
      : DEFAULT_SENTINEL;
  const override = affinity?.active_override ?? null;

  const onSelectCli = (cli: string) => {
    setSelectedCli(cli);
    setSelectedModel(
      override?.cli === cli && override.model ? override.model : DEFAULT_SENTINEL,
    );
  };

  const onSetOverride = () =>
    run(async () => {
      await setRouterOverride({
        workspace: slug,
        cli: selectedCli,
        model: selectedModel === DEFAULT_SENTINEL ? null : selectedModel,
        sticky: true,
      });
    });

  const onClearOverride = () =>
    run(async () => {
      await clearRouterOverride(slug);
    });

  const onEffortChange = (value: string) =>
    run(async () => {
      await putCliEffort(
        selectedCli,
        value === DEFAULT_SENTINEL ? null : value,
      );
    });

  const onToggleModel = (model: string, next: boolean) => {
    const full = selectedCap?.models ?? [];
    const updated = next
      ? Array.from(new Set([...enabledModels, model]))
      : enabledModels.filter((m) => m !== model);
    if (updated.length === 0) {
      setError("At least one model must stay enabled.");
      return;
    }
    // Canonical "all models enabled" is an ABSENT key (the backend clears
    // the key on an empty list); persisting an explicit full list would
    // drift from that, so collapse "all selected" back to [].
    const payload = updated.length >= full.length ? [] : updated;
    void run(async () => {
      await putCliEnabledModels(selectedCli, payload);
    });
  };

  const loaded = caps && affinity && config;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-surface rounded-2xl sm:max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading text-heading text-on-surface">
            Route this workspace
          </DialogTitle>
          <DialogDescription className="font-body text-body text-foreground-muted">
            Steer which CLI Self Jr picks next for{" "}
            <span className="font-mono text-on-surface-variant">{slug}</span>, and
            tune each CLI&apos;s model &amp; effort. Changes apply to the next
            selection, not the run already on screen.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <div
            role="alert"
            className="rounded-xl bg-error-container/40 text-on-error-container px-4 py-3 text-caption"
          >
            {error}
          </div>
        ) : null}

        {!loaded ? (
          <p className="text-caption text-foreground-muted py-8 text-center">
            {error ? "Couldn't load routing state." : "Loading routing state…"}
          </p>
        ) : (
          <div className="space-y-5">
            {/* Current routing */}
            <section className="space-y-2">
              <Label className="text-caption text-on-surface-variant uppercase tracking-wider">
                Current routing
              </Label>
              {override ? (
                <div className="flex items-center justify-between gap-3 rounded-lg border border-outline-variant/50 bg-surface-container-low px-3 py-2">
                  <span className="text-body text-on-surface">
                    Forced: <span className="font-mono">{override.cli}</span>
                    {override.model ? (
                      <span className="font-mono text-on-surface-variant">
                        {" "}
                        · {override.model}
                      </span>
                    ) : null}
                    {override.sticky ? (
                      <Badge variant="secondary" className="ml-2 align-middle">
                        sticky
                      </Badge>
                    ) : null}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={onClearOverride}
                  >
                    Clear
                  </Button>
                </div>
              ) : (
                <p className="text-caption text-foreground-muted">
                  Auto — the router picks by your override, quota, then affinity.
                </p>
              )}

              {affinity.candidates.length > 0 ? (
                <ul className="space-y-1 pt-1">
                  {affinity.candidates.map((c, i) => (
                    <li
                      key={`${c.cli}-${c.model}-${i}`}
                      className="flex items-center justify-between gap-2 text-caption"
                    >
                      <span className="text-on-surface-variant">
                        <span className="font-mono text-on-surface">{c.cli}</span>
                        {" · "}
                        <span className="font-mono">{c.model}</span>
                        {i === 0 && !override ? (
                          <Badge variant="outline" className="ml-2">
                            would pick
                          </Badge>
                        ) : null}
                      </span>
                      <span className="font-mono tabular-nums text-on-surface-variant">
                        {c.score.toFixed(2)} · {c.match_level} · {c.observations}
                        {" obs"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-caption text-foreground-muted">
                  No affinity history yet — the router falls back to defaults.
                </p>
              )}
            </section>

            <Separator />

            {/* Override picker (workspace-scoped) */}
            <section className="space-y-3">
              <Label className="text-caption text-on-surface-variant uppercase tracking-wider">
                Set override (this workspace)
              </Label>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label
                    htmlFor="cli-select"
                    className="text-caption text-foreground-muted"
                  >
                    CLI
                  </Label>
                  <Select value={selectedCli} onValueChange={onSelectCli}>
                    <SelectTrigger id="cli-select">
                      <SelectValue placeholder="Pick a CLI" />
                    </SelectTrigger>
                    <SelectContent>
                      {caps.map((c) => (
                        <SelectItem key={c.cli} value={c.cli}>
                          {c.cli}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label
                    htmlFor="model-select"
                    className="text-caption text-foreground-muted"
                  >
                    Model
                  </Label>
                  <Select
                    value={selectedModel}
                    onValueChange={setSelectedModel}
                    disabled={!selectedCap}
                  >
                    <SelectTrigger id="model-select">
                      <SelectValue placeholder="Model" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={DEFAULT_SENTINEL}>
                        CLI default
                        {selectedCap ? ` (${selectedCap.default_model})` : ""}
                      </SelectItem>
                      {selectedCap?.models.map((m) => (
                        <SelectItem key={m} value={m}>
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Button
                type="button"
                disabled={busy || !selectedCli}
                onClick={onSetOverride}
                className="bg-primary text-on-primary hover:opacity-90 w-full"
              >
                {busy ? "Applying…" : "Set override (sticky)"}
              </Button>
            </section>

            <Separator />

            {/* Per-CLI tuning (applies everywhere) */}
            {selectedCap ? (
              <section className="space-y-3">
                <Label className="text-caption text-on-surface-variant uppercase tracking-wider">
                  Tune {selectedCap.cli} (everywhere)
                </Label>

                <div className="space-y-1.5">
                  <Label
                    htmlFor="effort-select"
                    className="text-caption text-foreground-muted"
                  >
                    Effort
                  </Label>
                  {selectedCap.effort_levels.length > 0 ? (
                    <Select
                      value={currentEffort}
                      onValueChange={onEffortChange}
                      disabled={busy}
                    >
                      <SelectTrigger id="effort-select">
                        <SelectValue placeholder="Effort" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={DEFAULT_SENTINEL}>
                          CLI default
                          {selectedCap.default_effort
                            ? ` (${selectedCap.default_effort})`
                            : ""}
                        </SelectItem>
                        {selectedCap.effort_levels.map((lvl) => (
                          <SelectItem key={lvl} value={lvl}>
                            {lvl}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <p className="text-caption text-foreground-muted">
                      This CLI exposes no effort levels.
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label className="text-caption text-foreground-muted">
                    Enabled models
                  </Label>
                  <div className="space-y-1.5">
                    {selectedCap.models.map((m) => {
                      const isOn = enabledModels.includes(m);
                      const isLastOn = isOn && enabledModels.length === 1;
                      return (
                        <div
                          key={m}
                          className="flex items-center justify-between gap-3 rounded-md border border-outline-variant/40 px-3 py-1.5"
                        >
                          <span className="font-mono text-caption text-on-surface">
                            {m}
                            {m === selectedCap.default_model ? (
                              <span className="text-foreground-muted">
                                {" "}
                                · default
                              </span>
                            ) : null}
                          </span>
                          <Switch
                            checked={isOn}
                            disabled={busy || isLastOn}
                            onCheckedChange={(next) => onToggleModel(m, next)}
                            aria-label={`Toggle ${m}`}
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
              </section>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
