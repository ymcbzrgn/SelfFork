"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Play } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";

type Section =
  | "model"
  | "fine-tune"
  | "telegram"
  | "theme"
  | "workspace"
  | "advanced";

const DEFAULT_OPEN: Record<Section, boolean> = {
  model: true,
  "fine-tune": true,
  telegram: true,
  theme: false,
  workspace: false,
  advanced: false,
};

export default function SettingsPage() {
  const [open, setOpen] = useState<Record<Section, boolean>>(DEFAULT_OPEN);
  const [protocol, setProtocol] = useState<"openai" | "mlx" | "ollama">(
    "openai",
  );
  const [authKind, setAuthKind] = useState<"none" | "api-key" | "bearer">(
    "api-key",
  );
  const [datasetSource, setDatasetSource] = useState<"auto" | "manual">("auto");
  const [trainingEndpoint, setTrainingEndpoint] = useState<"same" | "separate">(
    "separate",
  );

  const toggle = (s: Section) =>
    setOpen((prev) => ({ ...prev, [s]: !prev[s] }));

  const SectionCard = ({
    id,
    title,
    children,
    previewWhenClosed,
  }: {
    id: Section;
    title: string;
    children: React.ReactNode;
    previewWhenClosed?: string;
  }) => (
    <section className="bg-surface rounded-xl shadow-sm border border-outline-variant/30 overflow-hidden">
      <button
        type="button"
        onClick={() => toggle(id)}
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

  return (
    <AppShell title="Settings">
      <main className="max-w-4xl mx-auto px-gutter-desktop py-vertical-gap space-y-4">
        <header className="mb-6">
          <h1 className="font-display text-display text-on-surface mb-2">
            Settings
          </h1>
          <p className="font-body text-caption text-on-surface-variant">
            Model endpoint, training, Telegram bridge, and operator preferences.
          </p>
        </header>

        <SectionCard id="model" title="Model Endpoint">
          <div className="pt-4 space-y-4">
            <FormRow label="Endpoint URL">
              <input
                type="text"
                defaultValue="http://192.168.1.10:8080"
                className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </FormRow>
            <FormRow label="Protocol">
              <RadioGroup
                value={protocol}
                onChange={(v) => setProtocol(v as typeof protocol)}
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
                defaultValue="gemma-4-26b-a4b-it-4bit"
                className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </FormRow>
            <FormRow label="Auth">
              <div className="space-y-2">
                <RadioGroup
                  value={authKind}
                  onChange={(v) => setAuthKind(v as typeof authKind)}
                  options={[
                    { v: "none", label: "None" },
                    { v: "api-key", label: "API key" },
                    { v: "bearer", label: "Bearer token" },
                  ]}
                  vertical
                />
                {authKind !== "none" && (
                  <input
                    type="password"
                    defaultValue="••••••••"
                    className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                )}
              </div>
            </FormRow>
            <div className="bg-success/5 border border-success/20 rounded-lg px-4 py-2 flex items-center gap-2 text-caption">
              <span className="w-2 h-2 rounded-full bg-success" />
              <span className="text-on-surface">
                Online · 187ms · just now
              </span>
            </div>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                className="px-4 py-2 border border-outline-variant text-caption font-medium rounded-lg hover:bg-surface-container-low"
              >
                Test connection
              </button>
              <button
                type="button"
                className="px-4 py-2 bg-primary text-white text-caption font-bold rounded-lg hover:bg-primary-container"
              >
                Save & restart
              </button>
            </div>
          </div>
        </SectionCard>

        <SectionCard id="fine-tune" title="Fine-tune">
          <div className="pt-4 space-y-5">
            <div>
              <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant mb-3">
                Training dataset
              </h4>
              <RadioGroup
                value={datasetSource}
                onChange={(v) => setDatasetSource(v as typeof datasetSource)}
                options={[
                  { v: "auto", label: "Auto from session history (recommended)" },
                  { v: "manual", label: "Manual path" },
                ]}
                vertical
              />
              {datasetSource === "manual" && (
                <input
                  type="text"
                  defaultValue="/path/to/dataset.jsonl"
                  className="w-full font-mono text-caption px-3 py-2 mt-2 bg-surface-container-low border border-outline-variant rounded-lg"
                />
              )}
              <p className="text-caption text-on-surface-variant tabular-nums mt-2">
                Examples: 8,432 (after CoT scoring) · Estimated time: 5h 18m on
                remote GPU
              </p>
            </div>

            <div>
              <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant mb-3">
                Hyperparams
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormRow label="Method">
                  <select className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg">
                    <option>QLoRA</option>
                    <option>LoRA</option>
                    <option>Full fine-tune</option>
                  </select>
                </FormRow>
                <FormRow label="Target modules">
                  <select className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg">
                    <option>attention only</option>
                    <option>attention + MLP</option>
                  </select>
                </FormRow>
                <FormRow label="LoRA rank">
                  <input
                    type="number"
                    defaultValue={32}
                    className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
                  />
                </FormRow>
                <FormRow label="LoRA alpha">
                  <input
                    type="number"
                    defaultValue={16}
                    className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
                  />
                </FormRow>
                <FormRow label="Learning rate">
                  <input
                    type="text"
                    defaultValue="2e-4"
                    className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg"
                  />
                </FormRow>
                <FormRow label="Epochs">
                  <input
                    type="number"
                    defaultValue={3}
                    className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums"
                  />
                </FormRow>
              </div>
            </div>

            <div>
              <h4 className="text-caption font-bold uppercase tracking-wider text-on-surface-variant mb-3">
                Training endpoint
              </h4>
              <RadioGroup
                value={trainingEndpoint}
                onChange={(v) =>
                  setTrainingEndpoint(v as typeof trainingEndpoint)
                }
                options={[
                  { v: "same", label: "Same as model endpoint" },
                  { v: "separate", label: "Separate" },
                ]}
                vertical
              />
              {trainingEndpoint === "separate" && (
                <input
                  type="text"
                  defaultValue="https://train.gpu.example.com"
                  className="w-full font-mono text-caption px-3 py-2 mt-2 bg-surface-container-low border border-outline-variant rounded-lg"
                />
              )}
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-outline-variant/30 flex-wrap gap-3">
              <p className="text-caption text-on-surface-variant">
                Current adapter:{" "}
                <span className="font-mono">v1.2</span> · 47 days old
              </p>
              <button
                type="button"
                className="px-5 py-2 bg-primary text-white text-caption font-bold rounded-lg hover:bg-primary-container flex items-center gap-1"
              >
                <Play className="h-4 w-4" strokeWidth={2} />
                Start training
              </button>
            </div>
          </div>
        </SectionCard>

        <SectionCard id="telegram" title="Telegram bridge">
          <div className="pt-4 space-y-4">
            <FormRow label="Soft confirmation window">
              <select className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg">
                <option>4 hours</option>
                <option>30 minutes</option>
                <option>1 hour</option>
                <option>2 hours</option>
                <option>8 hours</option>
              </select>
              <p className="text-[11px] text-on-surface-variant mt-1">
                Destructive action approval window. Silence = automatic cancel.
              </p>
            </FormRow>
            <FormRow label="Destructive whitelist">
              <button
                type="button"
                className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg hover:bg-surface-container-low"
              >
                Open editor →
              </button>
              <p className="text-[11px] text-on-surface-variant mt-1">
                7 categories enabled: prod_deploy · db_destructive · force_push ·
                file_destructive · account · financial · social_outbound
              </p>
            </FormRow>
            <FormRow label="Per-category override">
              <div className="space-y-2">
                <OverrideRow category="prod_deploy" defaultValue="4 hours" />
                <OverrideRow
                  category="social_outbound"
                  defaultValue="1 hour"
                />
                <button
                  type="button"
                  className="text-caption font-medium text-primary hover:underline"
                >
                  + Add override
                </button>
              </div>
            </FormRow>
            <a
              href="#"
              className="text-caption font-mono text-primary hover:underline"
            >
              → Open destructive_actions.yaml
            </a>
          </div>
        </SectionCard>

        <SectionCard
          id="theme"
          title="Theme"
          previewWhenClosed="Light enterprise · Inter"
        >
          <div className="pt-4 text-caption text-on-surface-variant">
            Theme picker coming soon. Light enterprise is the only ship in v3.
          </div>
        </SectionCard>

        <SectionCard
          id="workspace"
          title="Workspace defaults"
          previewWhenClosed="Kanban 4-column · Auto-save on"
        >
          <div className="pt-4 text-caption text-on-surface-variant">
            Kanban column names and auto-save behavior. Wire-in pending.
          </div>
        </SectionCard>

        <SectionCard
          id="advanced"
          title="Advanced (power user)"
          previewWhenClosed="Show raw thinking · Audit log · Vision tier · Reset RAG"
        >
          <div className="pt-4 space-y-2 text-caption text-on-surface">
            <Toggle label="Show Self Jr raw thinking" />
            <Toggle label="Show audit event timeline" />
            <Toggle label="Show vision tier details" />
            <Toggle label="Show full session log" />
          </div>
        </SectionCard>
      </main>
    </AppShell>
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

function RadioGroup({
  value,
  onChange,
  options,
  vertical = false,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { v: string; label: string }[];
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

function OverrideRow({
  category,
  defaultValue,
}: {
  category: string;
  defaultValue: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-caption w-40 text-on-surface">
        {category}
      </span>
      <select
        defaultValue={defaultValue}
        className="text-caption px-3 py-1.5 bg-surface-container-low border border-outline-variant rounded-lg"
      >
        <option>30 minutes</option>
        <option>1 hour</option>
        <option>2 hours</option>
        <option>4 hours</option>
        <option>8 hours</option>
      </select>
    </div>
  );
}

function Toggle({ label }: { label: string }) {
  const [on, setOn] = useState(false);
  return (
    <label className="flex items-center justify-between py-1">
      <span>{label}</span>
      <button
        type="button"
        onClick={() => setOn((x) => !x)}
        aria-pressed={on}
        className={`w-10 h-5 rounded-full transition-colors relative ${
          on ? "bg-primary" : "bg-surface-container-high"
        }`}
      >
        <span
          className={`absolute top-0.5 ${
            on ? "left-5" : "left-0.5"
          } w-4 h-4 rounded-full bg-white shadow transition-all`}
        />
      </button>
    </label>
  );
}
