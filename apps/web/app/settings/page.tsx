"use client";

import { ChevronDown, ChevronRight, Play } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type AutonomyPreset,
  type AutonomySettings,
  type CodexBarUserConfig,
  type DestructiveWhitelistResponse,
  type HeartbeatStateResponse,
  type ModelEndpointConfig,
  type ModelEndpointHealth,
  type ReflexAdapterInfo,
  type ReflexHyperParams,
  type StartTrainingPayload,
  applyHeartbeatPreset,
  getCodexBarSettings,
  getDestructiveWhitelist,
  getHeartbeatAutonomy,
  getHeartbeatState,
  getModelEndpoint,
  getReflexAdapterInfo,
  putCodexBarSettings,
  putDestructiveCategoryWindow,
  putDestructiveWhitelist,
  putHeartbeatAutonomy,
  putModelEndpoint,
  startTraining,
  testModelEndpoint,
} from "@/lib/api";
import { AppShell } from "@/components/layout/app-shell";

interface CodexBarStatus {
  state: string;
  binary: string | null;
  base_url: string | null;
  port: number | null;
  fail_reason: string | null;
}

type Section =
  | "model"
  | "fine-tune"
  | "telegram"
  | "codexbar"
  | "autonomy";

const DEFAULT_OPEN: Record<Section, boolean> = {
  model: true,
  "fine-tune": true,
  telegram: true,
  codexbar: false,
  autonomy: true,
};

const SAVE_WINDOW_OPTIONS = [
  { hours: 1, label: "1 hour" },
  { hours: 2, label: "2 hours" },
  { hours: 4, label: "4 hours" },
  { hours: 8, label: "8 hours" },
  { hours: 24, label: "24 hours" },
];

const DEFAULT_HYPERPARAMS: ReflexHyperParams = {
  method: "QLoRA",
  lora_rank: 32,
  lora_alpha: 16,
  learning_rate: "2e-4",
  epochs: 3,
  target_modules: "attention only",
};

export default function SettingsPage() {
  const [open, setOpen] = useState<Record<Section, boolean>>(DEFAULT_OPEN);
  const toggle = (s: Section) =>
    setOpen((prev) => ({ ...prev, [s]: !prev[s] }));

  return (
    <AppShell title="Settings">
      <main className="max-w-4xl mx-auto px-gutter-desktop py-vertical-gap space-y-4">
        <header className="mb-6">
          <h1 className="font-display text-display text-on-surface mb-2">
            Settings
          </h1>
          <p className="font-body text-caption text-on-surface-variant">
            Model endpoint, training, Telegram bridge, and autonomy
            preferences. Restart-required for most changes; the panels
            note where this applies.
          </p>
        </header>

        <SectionCard
          id="model"
          title="Model Endpoint"
          open={open}
          onToggle={toggle}
        >
          <ModelEndpointSection />
        </SectionCard>

        <SectionCard
          id="fine-tune"
          title="Fine-tune"
          open={open}
          onToggle={toggle}
        >
          <FineTuneSection />
        </SectionCard>

        <SectionCard
          id="telegram"
          title="Telegram bridge"
          open={open}
          onToggle={toggle}
        >
          <TelegramBridgeSection />
        </SectionCard>

        <SectionCard
          id="codexbar"
          title="CodexBar (secondary quota source)"
          previewWhenClosed="S-Quota Wave 2 — live + editable"
          open={open}
          onToggle={toggle}
        >
          <CodexBarSection />
        </SectionCard>

        <SectionCard
          id="autonomy"
          title="Autonomy — Heartbeat (S-Auto)"
          previewWhenClosed="Live daemon state + editable preset/knobs"
          open={open}
          onToggle={toggle}
        >
          <AutonomySection />
        </SectionCard>

        <p className="text-[11px] text-on-surface-variant italic">
          Vision adapter config lives on its own page →{" "}
          <a
            className="font-mono text-primary hover:underline"
            href="/cockpit/settings/vision"
          >
            /cockpit/settings/vision
          </a>
        </p>
      </main>
    </AppShell>
  );
}

// ── Reusable layout ────────────────────────────────────────────────────────

function SectionCard({
  id,
  title,
  children,
  previewWhenClosed,
  open,
  onToggle,
}: {
  id: Section;
  title: string;
  children: React.ReactNode;
  previewWhenClosed?: string;
  open: Record<Section, boolean>;
  onToggle: (s: Section) => void;
}) {
  return (
    <section className="bg-surface rounded-xl shadow-sm border border-outline-variant/30 overflow-hidden">
      <button
        type="button"
        onClick={() => onToggle(id)}
        aria-expanded={open[id]}
        className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-surface-container-low transition-colors group"
      >
        <span className="flex items-center gap-2 font-heading text-heading text-on-surface">
          {open[id] ? (
            <ChevronDown className="h-5 w-5 text-primary" strokeWidth={1.75} />
          ) : (
            <ChevronRight
              className="h-5 w-5 text-on-surface-variant/40 group-hover:text-primary"
              strokeWidth={1.75}
            />
          )}
          {title}
        </span>
        {!open[id] && previewWhenClosed && (
          <span className="text-caption text-on-surface-variant truncate ml-3">
            {previewWhenClosed}
          </span>
        )}
      </button>
      {open[id] && (
        <div className="px-6 pb-6 border-t border-outline-variant/20">
          {children}
        </div>
      )}
    </section>
  );
}

function FormRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="text-caption font-semibold text-on-surface mb-1.5 block">
        {label}
      </label>
      {children}
    </div>
  );
}

function RadioGroup<T extends string>({
  value,
  onChange,
  options,
  vertical = false,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { v: T; label: string }[];
  vertical?: boolean;
}) {
  return (
    <div className={vertical ? "space-y-1.5" : "flex items-center gap-4 flex-wrap"}>
      {options.map((o) => (
        <label
          key={o.v}
          className="flex items-center gap-2 text-caption cursor-pointer"
        >
          <input
            type="radio"
            checked={value === o.v}
            onChange={() => onChange(o.v)}
            className="w-4 h-4 accent-primary"
          />
          <span className="text-on-surface">{o.label}</span>
        </label>
      ))}
    </div>
  );
}

function HealthPill({ health }: { health: ModelEndpointHealth | null }) {
  if (health === null) {
    return (
      <div className="bg-surface-container-low border border-outline-variant/30 rounded-lg px-4 py-2 flex items-center gap-2 text-caption text-on-surface-variant italic">
        Click "Test connection" to probe the endpoint.
      </div>
    );
  }
  if (health.ok) {
    return (
      <div className="bg-success/5 border border-success/20 rounded-lg px-4 py-2 flex items-center gap-2 text-caption">
        <span className="w-2 h-2 rounded-full bg-success" />
        <span className="text-on-surface">
          Online · {health.latency_ms ?? "—"}ms · {health.detail || "ok"}
        </span>
      </div>
    );
  }
  return (
    <div className="bg-error/5 border border-error/20 rounded-lg px-4 py-2 flex items-center gap-2 text-caption">
      <span className="w-2 h-2 rounded-full bg-error" />
      <span className="text-on-surface">
        Unreachable · {health.latency_ms ?? "—"}ms · {health.detail}
      </span>
    </div>
  );
}

// ── Model Endpoint section ─────────────────────────────────────────────────

function ModelEndpointSection() {
  const [config, setConfig] = useState<ModelEndpointConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [health, setHealth] = useState<ModelEndpointHealth | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getModelEndpoint()
      .then((cfg) => {
        if (!cancelled) {
          setConfig(cfg);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = useCallback(async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await putModelEndpoint(config);
      setConfig(saved);
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  }, [config]);

  const handleTest = useCallback(async () => {
    if (!config) return;
    setTesting(true);
    setHealth(null);
    try {
      const result = await testModelEndpoint(config);
      setHealth(result);
    } catch (err) {
      setHealth({
        ok: false,
        status_code: null,
        latency_ms: null,
        detail: err instanceof Error ? err.message : "test failed",
      });
    } finally {
      setTesting(false);
    }
  }, [config]);

  if (loading) {
    return (
      <div className="pt-4 text-caption text-on-surface-variant italic">
        Loading saved endpoint…
      </div>
    );
  }
  if (error && !config) {
    return (
      <div className="pt-4 text-caption text-error">
        Failed to load: {error}
      </div>
    );
  }
  if (!config) return null;

  return (
    <div className="pt-4 space-y-4">
      <FormRow label="Endpoint URL">
        <input
          type="text"
          value={config.url}
          onChange={(e) =>
            setConfig({ ...config, url: e.target.value })
          }
          className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
      </FormRow>
      <FormRow label="Protocol">
        <RadioGroup<"openai" | "mlx" | "ollama">
          value={config.protocol}
          onChange={(v) => setConfig({ ...config, protocol: v })}
          options={[
            { v: "openai", label: "OpenAI-compatible" },
            { v: "mlx", label: "MLX-server (raw)" },
            { v: "ollama", label: "Ollama" },
          ]}
        />
      </FormRow>
      <FormRow label="Model name">
        <input
          type="text"
          value={config.model_name}
          onChange={(e) =>
            setConfig({ ...config, model_name: e.target.value })
          }
          className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
      </FormRow>
      <FormRow label="Auth">
        <div className="space-y-2">
          <RadioGroup<"none" | "api-key" | "bearer">
            value={config.auth_kind}
            onChange={(v) => setConfig({ ...config, auth_kind: v })}
            options={[
              { v: "none", label: "None" },
              { v: "api-key", label: "API key" },
              { v: "bearer", label: "Bearer token" },
            ]}
            vertical
          />
          {config.auth_kind !== "none" && (
            <input
              type="password"
              value={config.auth_secret}
              onChange={(e) =>
                setConfig({ ...config, auth_secret: e.target.value })
              }
              placeholder="Secret (stored plain in ~/.selffork/settings/)"
              className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          )}
        </div>
      </FormRow>
      <HealthPill health={health} />
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-[11px] text-on-surface-variant italic">
          Saved to ~/.selffork/settings/model-endpoint.yaml. Effect on
          next dashboard restart.
        </p>
        <div className="flex items-center gap-2">
          {savedAt && !saving && (
            <span className="text-caption text-success">Saved ✓</span>
          )}
          {error && !saving && (
            <span className="text-caption text-error">{error}</span>
          )}
          <button
            type="button"
            disabled={testing}
            onClick={() => void handleTest()}
            className="px-4 py-2 border border-outline-variant text-caption font-medium rounded-lg hover:bg-surface-container-low disabled:opacity-50"
          >
            {testing ? "Testing…" : "Test connection"}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void handleSave()}
            className="px-4 py-2 bg-primary text-white text-caption font-bold rounded-lg hover:bg-primary-container disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Fine-tune section ──────────────────────────────────────────────────────

function FineTuneSection() {
  const [adapter, setAdapter] = useState<ReflexAdapterInfo | null>(null);
  const [adapterError, setAdapterError] = useState<string | null>(null);
  const [hyperparams, setHyperparams] = useState<ReflexHyperParams>(
    DEFAULT_HYPERPARAMS,
  );
  const [datasetSource, setDatasetSource] = useState<"auto" | "manual">(
    "auto",
  );
  const [datasetPath, setDatasetPath] = useState("");
  const [trainingEndpointKind, setTrainingEndpointKind] = useState<
    "same" | "separate"
  >("same");
  const [trainingEndpoint, setTrainingEndpoint] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [lastJobId, setLastJobId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getReflexAdapterInfo()
      .then((info) => !cancelled && setAdapter(info))
      .catch(
        (err: Error) => !cancelled && setAdapterError(err.message),
      );
    return () => {
      cancelled = true;
    };
  }, []);

  const handleStart = useCallback(async () => {
    setSubmitting(true);
    setSubmitError(null);
    const payload: StartTrainingPayload = {
      dataset_source: datasetSource,
      dataset_path:
        datasetSource === "manual" ? datasetPath || undefined : undefined,
      hyperparams,
      training_endpoint:
        trainingEndpointKind === "separate"
          ? trainingEndpoint
          : undefined,
    };
    try {
      const job = await startTraining(payload);
      setLastJobId(job.job_id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "submit failed");
    } finally {
      setSubmitting(false);
    }
  }, [
    datasetSource,
    datasetPath,
    hyperparams,
    trainingEndpoint,
    trainingEndpointKind,
  ]);

  return (
    <div className="pt-4 space-y-5">
      <div>
        <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant mb-3">
          Training dataset
        </h4>
        <RadioGroup<"auto" | "manual">
          value={datasetSource}
          onChange={setDatasetSource}
          options={[
            { v: "auto", label: "Auto from session history (recommended)" },
            { v: "manual", label: "Manual path" },
          ]}
          vertical
        />
        {datasetSource === "manual" && (
          <input
            type="text"
            value={datasetPath}
            onChange={(e) => setDatasetPath(e.target.value)}
            placeholder="/path/to/dataset.jsonl"
            className="w-full font-mono text-caption px-3 py-2 mt-2 bg-surface-container-low border border-outline-variant rounded-lg"
          />
        )}
      </div>

      <div>
        <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant mb-3">
          Hyperparams
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FormRow label="Method">
            <select
              value={hyperparams.method}
              onChange={(e) =>
                setHyperparams({
                  ...hyperparams,
                  method: e.target.value as ReflexHyperParams["method"],
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
            >
              <option>QLoRA</option>
              <option>LoRA</option>
              <option>Full</option>
            </select>
          </FormRow>
          <FormRow label="Target modules">
            <select
              value={hyperparams.target_modules}
              onChange={(e) =>
                setHyperparams({
                  ...hyperparams,
                  target_modules: e.target
                    .value as ReflexHyperParams["target_modules"],
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
            >
              <option>attention only</option>
              <option>attention + MLP</option>
            </select>
          </FormRow>
          <FormRow label="LoRA rank">
            <input
              type="number"
              value={hyperparams.lora_rank}
              onChange={(e) =>
                setHyperparams({
                  ...hyperparams,
                  lora_rank: Number(e.target.value) || 0,
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
            />
          </FormRow>
          <FormRow label="LoRA alpha">
            <input
              type="number"
              value={hyperparams.lora_alpha}
              onChange={(e) =>
                setHyperparams({
                  ...hyperparams,
                  lora_alpha: Number(e.target.value) || 0,
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
            />
          </FormRow>
          <FormRow label="Learning rate">
            <input
              type="text"
              value={hyperparams.learning_rate}
              onChange={(e) =>
                setHyperparams({
                  ...hyperparams,
                  learning_rate: e.target.value,
                })
              }
              className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
            />
          </FormRow>
          <FormRow label="Epochs">
            <input
              type="number"
              value={hyperparams.epochs}
              onChange={(e) =>
                setHyperparams({
                  ...hyperparams,
                  epochs: Number(e.target.value) || 0,
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
            />
          </FormRow>
        </div>
      </div>

      <div>
        <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant mb-3">
          Training endpoint
        </h4>
        <RadioGroup<"same" | "separate">
          value={trainingEndpointKind}
          onChange={setTrainingEndpointKind}
          options={[
            { v: "same", label: "Same as model endpoint" },
            { v: "separate", label: "Separate" },
          ]}
          vertical
        />
        {trainingEndpointKind === "separate" && (
          <input
            type="text"
            value={trainingEndpoint}
            onChange={(e) => setTrainingEndpoint(e.target.value)}
            placeholder="https://train.gpu.example.com"
            className="w-full font-mono text-caption px-3 py-2 mt-2 bg-surface-container-low border border-outline-variant rounded-lg"
          />
        )}
      </div>

      <div className="pt-4 border-t border-outline-variant/30 flex items-center justify-between flex-wrap gap-3">
        <div className="text-caption text-on-surface-variant">
          <AdapterStatus adapter={adapter} error={adapterError} />
        </div>
        <div className="flex items-center gap-3">
          {lastJobId && (
            <span className="text-caption text-on-surface-variant">
              Queued · job{" "}
              <span className="font-mono">{lastJobId}</span> (M7 worker
              pending)
            </span>
          )}
          {submitError && (
            <span className="text-caption text-error">{submitError}</span>
          )}
          <button
            type="button"
            disabled={submitting}
            onClick={() => void handleStart()}
            className="px-5 py-2 bg-primary text-white text-caption font-bold rounded-lg hover:bg-primary-container flex items-center gap-1 disabled:opacity-50"
          >
            <Play className="h-4 w-4" strokeWidth={2} />
            {submitting ? "Queueing…" : "Start training"}
          </button>
        </div>
      </div>
    </div>
  );
}

function AdapterStatus({
  adapter,
  error,
}: {
  adapter: ReflexAdapterInfo | null;
  error: string | null;
}) {
  if (error) {
    return <span className="text-error">Adapter status: {error}</span>;
  }
  if (!adapter) {
    return <span className="italic">Reading adapter manifest…</span>;
  }
  if (!adapter.adapter_trained) {
    return (
      <span>
        Current adapter: <span className="italic">{adapter.message ?? "none"}</span>
      </span>
    );
  }
  return (
    <span>
      Current adapter:{" "}
      <span className="font-mono">{adapter.version ?? "?"}</span>
      {adapter.age_days !== null && ` · ${adapter.age_days} days old`}
      {adapter.method && ` · ${adapter.method}`}
      {adapter.examples !== null && ` · ${adapter.examples} examples`}
    </span>
  );
}

// ── Telegram bridge section ─────────────────────────────────────────────────

function TelegramBridgeSection() {
  const [whitelist, setWhitelist] =
    useState<DestructiveWhitelistResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorText, setEditorText] = useState("");
  const [editorBusy, setEditorBusy] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getDestructiveWhitelist();
      setWhitelist(data);
      setEditorText(data.raw_yaml);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleCategoryWindow = useCallback(
    async (categoryId: string, hours: number) => {
      try {
        const updated = await putDestructiveCategoryWindow(
          categoryId,
          hours,
        );
        setWhitelist(updated);
        setEditorText(updated.raw_yaml);
      } catch (err) {
        setError(err instanceof Error ? err.message : "update failed");
      }
    },
    [],
  );

  const handleEditorSave = useCallback(async () => {
    setEditorBusy(true);
    setEditorError(null);
    try {
      const updated = await putDestructiveWhitelist(editorText);
      setWhitelist(updated);
      setEditorText(updated.raw_yaml);
      setEditorOpen(false);
    } catch (err) {
      setEditorError(err instanceof Error ? err.message : "save failed");
    } finally {
      setEditorBusy(false);
    }
  }, [editorText]);

  if (error && !whitelist) {
    return (
      <div className="pt-4 text-caption text-error">
        Failed to load destructive whitelist: {error}
      </div>
    );
  }
  if (!whitelist) {
    return (
      <div className="pt-4 text-caption text-on-surface-variant italic">
        Loading destructive whitelist…
      </div>
    );
  }

  return (
    <div className="pt-4 space-y-4">
      <FormRow label="Destructive whitelist">
        <p className="text-[11px] text-on-surface-variant mt-1">
          {whitelist.categories.length} categor
          {whitelist.categories.length === 1 ? "y" : "ies"} enabled (
          <span className="font-mono">{whitelist.source}</span>) ·{" "}
          {whitelist.categories.map((c) => c.id).join(" · ")}
        </p>
        <div className="flex items-center gap-2 mt-2">
          <button
            type="button"
            onClick={() => setEditorOpen((x) => !x)}
            className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg hover:bg-surface-container-low"
          >
            {editorOpen ? "Close editor" : "Open editor →"}
          </button>
          <span className="text-[11px] text-on-surface-variant font-mono">
            {whitelist.path}
          </span>
        </div>
      </FormRow>
      {editorOpen && (
        <div className="space-y-2">
          <textarea
            rows={16}
            value={editorText}
            onChange={(e) => setEditorText(e.target.value)}
            className="w-full font-mono text-[12px] px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          {editorError && (
            <p className="text-caption text-error">{editorError}</p>
          )}
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setEditorText(whitelist.raw_yaml);
                setEditorError(null);
              }}
              className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg"
            >
              Revert to saved
            </button>
            <button
              type="button"
              disabled={editorBusy}
              onClick={() => void handleEditorSave()}
              className="px-3 py-1.5 bg-primary text-white text-caption font-bold rounded-lg disabled:opacity-50"
            >
              {editorBusy ? "Saving…" : "Save whitelist"}
            </button>
          </div>
        </div>
      )}
      <FormRow label="Per-category soft-confirm window">
        <div className="space-y-2">
          {whitelist.categories.map((cat) => (
            <CategoryWindowRow
              key={cat.id}
              category={cat.id}
              currentHours={cat.confirm_window_hours}
              onChange={(h) => void handleCategoryWindow(cat.id, h)}
            />
          ))}
        </div>
      </FormRow>
    </div>
  );
}

function CategoryWindowRow({
  category,
  currentHours,
  onChange,
}: {
  category: string;
  currentHours: number;
  onChange: (hours: number) => void;
}) {
  const matched = useMemo(
    () =>
      SAVE_WINDOW_OPTIONS.find(
        (o) => Math.abs(o.hours - currentHours) < 0.001,
      ),
    [currentHours],
  );
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-caption w-44 text-on-surface">
        {category}
      </span>
      <select
        value={matched?.label ?? "Custom"}
        onChange={(e) => {
          const found = SAVE_WINDOW_OPTIONS.find(
            (o) => o.label === e.target.value,
          );
          if (found) onChange(Math.round(found.hours));
        }}
        className="text-caption px-3 py-1.5 bg-surface-container-low border border-outline-variant rounded-lg"
      >
        {SAVE_WINDOW_OPTIONS.map((o) => (
          <option key={o.label}>{o.label}</option>
        ))}
        {!matched && <option>Custom ({currentHours}h)</option>}
      </select>
    </div>
  );
}

// ── CodexBar section ───────────────────────────────────────────────────────

function CodexBarSection() {
  const [status, setStatus] = useState<CodexBarStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [config, setConfig] = useState<CodexBarUserConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch("/api/codexbar/status");
        if (!res.ok) throw new Error(`http_${res.status}`);
        const data = (await res.json()) as CodexBarStatus;
        if (!cancelled) {
          setStatus(data);
          setStatusError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setStatusError(err instanceof Error ? err.message : "fetch_failed");
        }
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getCodexBarSettings()
      .then((cfg) => !cancelled && setConfig(cfg))
      .catch(
        (err: Error) => !cancelled && setConfigError(err.message),
      );
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = useCallback(async () => {
    if (!config) return;
    setSaving(true);
    try {
      const saved = await putCodexBarSettings(config);
      setConfig(saved);
      setSavedAt(Date.now());
      setConfigError(null);
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  }, [config]);

  const stateColor: Record<string, string> = {
    ready: "text-success",
    starting: "text-amber-600",
    stopping: "text-amber-600",
    stopped: "text-on-surface-variant",
    inactive: "text-on-surface-variant",
    failed: "text-error",
    disabled: "text-on-surface-variant",
  };
  const color = status ? stateColor[status.state] ?? "text-on-surface" : "";

  return (
    <div className="pt-4 space-y-4 text-caption text-on-surface">
      {/* Live status */}
      {statusError ? (
        <div className="italic text-on-surface-variant">
          Couldn't reach /api/codexbar/status ({statusError}). Dashboard
          running?
        </div>
      ) : !status ? (
        <div className="italic text-on-surface-variant">
          Reading sidecar state…
        </div>
      ) : (
        <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
          <div className="flex gap-2">
            <dt className="text-on-surface-variant w-28">State:</dt>
            <dd className={`${color} font-bold uppercase tracking-wide`}>
              {status.state}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-on-surface-variant w-28">Port:</dt>
            <dd className="font-mono">{status.port ?? "—"}</dd>
          </div>
          <div className="flex gap-2 md:col-span-2">
            <dt className="text-on-surface-variant w-28">Binary:</dt>
            <dd className="font-mono break-all">
              {status.binary ?? (
                <span className="text-on-surface-variant/60 italic">
                  not resolved (set SELFFORK_CODEXBAR_ENABLED=false or
                  install)
                </span>
              )}
            </dd>
          </div>
          <div className="flex gap-2 md:col-span-2">
            <dt className="text-on-surface-variant w-28">Base URL:</dt>
            <dd className="font-mono break-all">{status.base_url ?? "—"}</dd>
          </div>
          {status.fail_reason && (
            <div className="flex gap-2 md:col-span-2">
              <dt className="text-on-surface-variant w-28">Last error:</dt>
              <dd className="text-error">{status.fail_reason}</dd>
            </div>
          )}
        </dl>
      )}

      {/* Settings form */}
      <div className="pt-3 border-t border-outline-variant/30 space-y-3">
        <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant">
          User-tunable knobs (restart-required)
        </h4>
        {configError && !config && (
          <p className="text-error">{configError}</p>
        )}
        {config && (
          <>
            <FormRow label="Version pin (empty = vendored manifest default)">
              <input
                type="text"
                value={config.version_pin}
                onChange={(e) =>
                  setConfig({ ...config, version_pin: e.target.value })
                }
                placeholder="v0.27.0"
                className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
              />
            </FormRow>
            <FormRow label="Binary path override (empty = PATH search + vendored fallback)">
              <input
                type="text"
                value={config.binary_path_override}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    binary_path_override: e.target.value,
                  })
                }
                placeholder="/usr/local/bin/codexbar"
                className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
              />
            </FormRow>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.auto_update}
                onChange={(e) =>
                  setConfig({ ...config, auto_update: e.target.checked })
                }
                className="w-4 h-4 accent-primary"
              />
              <span>
                Opt in to weekly codexbar-watch auto-update PRs
              </span>
            </label>
            <div className="flex items-center justify-end gap-2">
              {savedAt && !saving && (
                <span className="text-success">Saved ✓</span>
              )}
              {configError && !saving && (
                <span className="text-error">{configError}</span>
              )}
              <button
                type="button"
                disabled={saving}
                onClick={() => void handleSave()}
                className="px-4 py-2 bg-primary text-white text-caption font-bold rounded-lg disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Autonomy section ────────────────────────────────────────────────────────

function AutonomySection() {
  const [autonomy, setAutonomy] = useState<AutonomySettings | null>(null);
  const [state, setState] = useState<HeartbeatStateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const [a, s] = await Promise.all([
          getHeartbeatAutonomy(),
          getHeartbeatState(),
        ]);
        if (!cancelled) {
          setAutonomy(a);
          setState(s);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "fetch_failed");
        }
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const applyPreset = useCallback(async (preset: AutonomyPreset) => {
    setSaving(true);
    try {
      const updated = await applyHeartbeatPreset(preset);
      setAutonomy(updated);
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "preset failed");
    } finally {
      setSaving(false);
    }
  }, []);

  const handleSave = useCallback(async () => {
    if (!autonomy) return;
    setSaving(true);
    try {
      const saved = await putHeartbeatAutonomy(autonomy);
      setAutonomy(saved);
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  }, [autonomy]);

  const stateColor: Record<string, string> = {
    running: "text-success",
    starting: "text-amber-600",
    stopping: "text-amber-600",
    stopped: "text-on-surface-variant",
    inactive: "text-on-surface-variant",
    disabled: "text-on-surface-variant",
    failed: "text-error",
  };
  const airColor: Record<string, string> = {
    medium: "text-amber-600",
    high: "text-error",
    critical: "text-error",
  };

  if (error && !autonomy) {
    return (
      <div className="pt-4 italic text-on-surface-variant text-caption">
        Couldn't reach /api/heartbeat/* ({error}).
      </div>
    );
  }
  if (!autonomy || !state) {
    return (
      <div className="pt-4 italic text-on-surface-variant text-caption">
        Reading heartbeat state…
      </div>
    );
  }

  const daemonColor = stateColor[state.state] ?? "text-on-surface";

  return (
    <div className="pt-4 space-y-4 text-caption text-on-surface">
      <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
        <div className="flex gap-2">
          <dt className="text-on-surface-variant w-36">Daemon state:</dt>
          <dd className={`${daemonColor} font-bold uppercase tracking-wide`}>
            {state.state}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-on-surface-variant w-36">Tick count:</dt>
          <dd className="font-mono">{state.tick_count}</dd>
        </div>
      </dl>

      <div className="pt-3 border-t border-outline-variant/30 space-y-3">
        <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant">
          Preset
        </h4>
        <div className="flex gap-2 flex-wrap">
          {(["kapalı", "denetimli", "dengeli", "tam"] as AutonomyPreset[]).map(
            (preset) => (
              <button
                key={preset}
                type="button"
                disabled={saving}
                onClick={() => void applyPreset(preset)}
                className={`px-3 py-1.5 text-caption font-medium rounded-lg border ${
                  autonomy.preset === preset
                    ? "bg-primary text-white border-primary"
                    : "border-outline-variant hover:bg-surface-container-low"
                }`}
              >
                {preset}
              </button>
            ),
          )}
        </div>
      </div>

      <div className="pt-3 border-t border-outline-variant/30 space-y-3">
        <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant">
          Power-user knobs
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FormRow label="Creative dial">
            <select
              value={autonomy.creative_dial}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  creative_dial: e.target
                    .value as AutonomySettings["creative_dial"],
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
            >
              <option value="closed">closed</option>
              <option value="spark_only">spark_only</option>
              <option value="gradient">gradient</option>
              <option value="full">full</option>
            </select>
          </FormRow>
          <FormRow label="Creative veto window (hours)">
            <input
              type="number"
              min={1}
              max={72}
              value={autonomy.creative_veto_window_hours}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  creative_veto_window_hours: Number(e.target.value) || 1,
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
            />
          </FormRow>
          <FormRow label="Tick (s)">
            <input
              type="number"
              step="0.1"
              value={autonomy.tick_seconds}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  tick_seconds: Number(e.target.value) || 0.05,
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
            />
          </FormRow>
          <FormRow label="Reconciliation (s)">
            <input
              type="number"
              value={autonomy.reconciliation_seconds}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  reconciliation_seconds: Number(e.target.value) || 10,
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
            />
          </FormRow>
          <FormRow label="Concurrency cap">
            <input
              type="number"
              min={1}
              value={autonomy.max_concurrency}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  max_concurrency: Number(e.target.value) || 1,
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
            />
          </FormRow>
          <FormRow label="Active hours">
            <input
              type="text"
              value={autonomy.active_hours}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  active_hours: e.target.value,
                })
              }
              placeholder="08:00-23:59"
              className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
            />
          </FormRow>
          <FormRow label="Timezone">
            <input
              type="text"
              value={autonomy.timezone}
              onChange={(e) =>
                setAutonomy({ ...autonomy, timezone: e.target.value })
              }
              placeholder="Europe/Istanbul"
              className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
            />
          </FormRow>
          <FormRow label="Morning report time">
            <input
              type="text"
              value={autonomy.morning_report_time}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  morning_report_time: e.target.value,
                })
              }
              placeholder="08:00"
              className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
            />
          </FormRow>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autonomy.enabled}
              onChange={(e) =>
                setAutonomy({ ...autonomy, enabled: e.target.checked })
              }
              className="w-4 h-4 accent-primary"
            />
            <span>Enabled</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autonomy.supervised_mode}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  supervised_mode: e.target.checked,
                })
              }
              className="w-4 h-4 accent-primary"
            />
            <span>Supervised (Denetimli)</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autonomy.morning_report_enabled}
              onChange={(e) =>
                setAutonomy({
                  ...autonomy,
                  morning_report_enabled: e.target.checked,
                })
              }
              className="w-4 h-4 accent-primary"
            />
            <span>Morning report</span>
          </label>
        </div>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <p className="text-[11px] text-on-surface-variant italic">
            Persisted to ~/.selffork/heartbeat/autonomy.yaml. Effect on
            next daemon restart (hot-reload deferred).
          </p>
          <div className="flex items-center gap-2">
            {savedAt && !saving && (
              <span className="text-success">Saved ✓</span>
            )}
            {error && !saving && (
              <span className="text-error">{error}</span>
            )}
            <button
              type="button"
              disabled={saving}
              onClick={() => void handleSave()}
              className="px-4 py-2 bg-primary text-white text-caption font-bold rounded-lg disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save knobs"}
            </button>
          </div>
        </div>
      </div>

      {state.last_decision && (
        <div className="rounded border border-outline-variant/40 px-3 py-2 bg-surface-1">
          <div className="text-on-surface-variant text-[11px] uppercase tracking-wide mb-1">
            Last decision
          </div>
          <div>
            <span className="font-mono">{state.last_decision.action}</span>
            {state.last_decision.fallback && (
              <span className="ml-2 text-amber-600">(fallback)</span>
            )}
          </div>
          <div className="text-on-surface-variant text-[12px] mt-1">
            {state.last_decision.reasoning}
          </div>
        </div>
      )}

      {state.last_result && (
        <div className="rounded border border-outline-variant/40 px-3 py-2 bg-surface-1">
          <div className="text-on-surface-variant text-[11px] uppercase tracking-wide mb-1">
            Last result
          </div>
          <div>
            <span className="font-mono">{state.last_result.action}</span>
            <span className="ml-2 uppercase tracking-wide">
              {state.last_result.outcome}
            </span>
          </div>
          <div className="text-on-surface-variant text-[12px] mt-1">
            {state.last_result.summary}
          </div>
        </div>
      )}

      {state.last_air_alert && (
        <div className="rounded border border-error/60 px-3 py-2 bg-error/10">
          <div
            className={`${airColor[state.last_air_alert.severity] ?? "text-error"} text-[11px] uppercase tracking-wide mb-1 font-bold`}
          >
            🚨 AIR alert · {state.last_air_alert.severity}
          </div>
          <div className="text-[12px]">
            {state.last_air_alert.reason} (consecutive failures:{" "}
            {state.last_air_alert.consecutive_failures})
          </div>
          <div className="text-on-surface-variant text-[12px] mt-1">
            {state.last_air_alert.recommended_recovery}
          </div>
        </div>
      )}
    </div>
  );
}
