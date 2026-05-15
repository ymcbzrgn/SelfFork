/**
 * Cockpit Settings → Vision (M5+ — config-driven model selection).
 *
 * Operator-facing UI for swapping the MLX and Ollama vision adapters'
 * model identifiers without editing YAML by hand. "Auto-detect" probes
 * the running mlx_vlm.server and Ollama daemon for available IDs.
 *
 * Reads / writes ``selffork.yaml`` via the orchestrator dashboard:
 *   GET    /api/settings/vision         → current config
 *   POST   /api/settings/vision         → partial update + YAML write
 *   POST   /api/settings/vision/detect  → adapter probe
 */
"use client";

import { useEffect, useId, useState } from "react";

import { API_BASE } from "@/lib/api";

type VisionConfig = {
  mlx_model_id: string;
  mlx_server_url: string;
  ollama_model_tag: string;
  ollama_host: string;
  auto_detect: boolean;
};

type DetectResponse = {
  mlx_available: boolean;
  mlx_models: string[];
  mlx_error: string | null;
  ollama_available: boolean;
  ollama_models: string[];
  ollama_error: string | null;
};

const DEFAULT_CONFIG: VisionConfig = {
  mlx_model_id: "mlx-community/gemma-4-E2B-it-4bit",
  mlx_server_url: "http://127.0.0.1:8080",
  ollama_model_tag: "gemma4:e2b-q4_K_M",
  ollama_host: "http://127.0.0.1:11434",
  auto_detect: true,
};

/**
 * Format a FastAPI error ``detail`` for display. Pydantic 422 returns an array
 * of ``{loc, msg, type}`` records; rendering the array as-is yields
 * ``[object Object]``. This helper flattens the array into a "; "-joined list
 * of ``msg`` strings and falls back to JSON for unknown shapes.
 */
function formatPydanticDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) =>
        d && typeof d === "object" && "msg" in d
          ? String((d as { msg: unknown }).msg)
          : JSON.stringify(d),
      )
      .join("; ");
  }
  if (detail !== null && detail !== undefined) return JSON.stringify(detail);
  return fallback;
}

export default function VisionSettingsPage() {
  const [cfg, setCfg] = useState<VisionConfig | null>(null);
  const [detect, setDetect] = useState<DetectResponse | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/settings/vision`)
      .then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`GET ${r.status}`)),
      )
      .then((data: VisionConfig) => {
        if (cancelled) return;
        setCfg(data);
        if (data.auto_detect) void runDetect();
      })
      .catch((e) => {
        if (!cancelled) {
          setError(`load: ${e.message ?? e}`);
          setCfg(DEFAULT_CONFIG);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runDetect = async () => {
    setDetecting(true);
    setError(null);
    let cancelled = false;
    try {
      const r = await fetch(`${API_BASE}/api/settings/vision/detect`, { method: "POST" });
      if (!r.ok) throw new Error(`POST detect ${r.status}`);
      const payload = (await r.json()) as DetectResponse;
      if (!cancelled) setDetect(payload);
    } catch (e) {
      if (!cancelled) setError(`detect: ${(e as Error).message}`);
    } finally {
      if (!cancelled) setDetecting(false);
    }
    return () => {
      cancelled = true;
    };
  };

  const handleSave = async () => {
    if (!cfg) return;
    setSaving(true);
    setError(null);
    setInfo(null);
    try {
      const r = await fetch(`${API_BASE}/api/settings/vision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(
          `POST ${r.status}: ${formatPydanticDetail(body.detail, r.statusText)}`,
        );
      }
      const updated = (await r.json()) as VisionConfig;
      setCfg(updated);
      setInfo("Saved. Restart any in-flight sessions to pick up the new adapter defaults.");
    } catch (e) {
      setError(`save: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  if (!cfg) {
    return (
      <div className="p-6 text-sm text-zinc-500">Loading vision config…</div>
    );
  }

  return (
    <div
      className="p-6 space-y-6 max-w-3xl"
      data-testid="vision-settings-page"
    >
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Vision Adapters</h1>
        <p className="text-sm text-zinc-500">
          Body pillar (M5) vision model configuration. Changes write to{" "}
          <code className="text-xs bg-zinc-100 px-1 rounded">
            selffork.yaml
          </code>{" "}
          and reload adapter defaults; in-flight sessions must restart to
          pick up the new IDs.
        </p>
      </header>

      {error && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded bg-red-50 text-red-700 px-3 py-2 text-sm"
        >
          {error}
        </div>
      )}
      {info && (
        <div
          role="status"
          aria-live="polite"
          className="rounded bg-green-50 text-green-800 px-3 py-2 text-sm"
        >
          {info}
        </div>
      )}

      <AdapterCard
        title="MLX (Apple Silicon — Tier 1)"
        status={
          detect ? (detect.mlx_available ? "available" : "unreachable") : null
        }
        statusColour={detect?.mlx_available}
        errorMsg={detect?.mlx_error ?? null}
      >
        <Field
          label="Model ID"
          value={cfg.mlx_model_id}
          options={detect?.mlx_models}
          onChange={(v) => setCfg({ ...cfg, mlx_model_id: v })}
          datalistId="mlx-models"
          testId="mlx-model-id"
        />
        <Field
          label="Server URL"
          value={cfg.mlx_server_url}
          onChange={(v) => setCfg({ ...cfg, mlx_server_url: v })}
          testId="mlx-server-url"
        />
      </AdapterCard>

      <AdapterCard
        title="Ollama (Linux fallback)"
        status={
          detect
            ? detect.ollama_available
              ? "available"
              : "unreachable"
            : null
        }
        statusColour={detect?.ollama_available}
        errorMsg={detect?.ollama_error ?? null}
      >
        <Field
          label="Model tag"
          value={cfg.ollama_model_tag}
          options={detect?.ollama_models}
          onChange={(v) => setCfg({ ...cfg, ollama_model_tag: v })}
          datalistId="ollama-models"
          testId="ollama-model-tag"
        />
        <Field
          label="Host"
          value={cfg.ollama_host}
          onChange={(v) => setCfg({ ...cfg, ollama_host: v })}
          testId="ollama-host"
        />
      </AdapterCard>

      <section className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cfg.auto_detect}
            onChange={(e) => setCfg({ ...cfg, auto_detect: e.target.checked })}
            data-testid="auto-detect-toggle"
          />
          Auto-detect when this page loads
        </label>
      </section>

      <div className="flex gap-2">
        <button
          type="button"
          className="rounded px-4 py-2 bg-zinc-100 hover:bg-zinc-200 disabled:opacity-50 text-sm"
          disabled={detecting || saving}
          onClick={() => void runDetect()}
          data-testid="detect-button"
        >
          {detecting ? "Detecting…" : "Auto-detect models"}
        </button>
        <button
          type="button"
          className="rounded px-4 py-2 bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 text-sm"
          disabled={saving || detecting}
          onClick={() => void handleSave()}
          data-testid="save-button"
        >
          {saving ? "Saving…" : "Apply"}
        </button>
      </div>
    </div>
  );
}

function AdapterCard({
  title,
  status,
  statusColour,
  errorMsg,
  children,
}: {
  title: string;
  status: string | null;
  statusColour: boolean | undefined;
  errorMsg: string | null;
  children: React.ReactNode;
}) {
  const statusClass =
    statusColour === true
      ? "text-green-600"
      : statusColour === false
        ? "text-amber-700"
        : "text-zinc-400";
  return (
    <section
      className="space-y-3 border rounded p-4"
      data-testid={`adapter-card-${title.split(" ")[0].toLowerCase()}`}
    >
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-sm">{title}</h2>
        <span className={`text-xs ${statusClass}`}>{status ?? "—"}</span>
      </div>
      {children}
      {errorMsg && (
        <div className="text-xs text-amber-700 break-words">{errorMsg}</div>
      )}
    </section>
  );
}

function Field({
  label,
  value,
  options,
  onChange,
  datalistId,
  testId,
}: {
  label: string;
  value: string;
  options?: string[];
  onChange: (v: string) => void;
  datalistId?: string;
  testId?: string;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label
        htmlFor={id}
        className="block text-xs font-medium uppercase tracking-wider text-zinc-500"
      >
        {label}
      </label>
      <input
        id={id}
        type="text"
        className="w-full border rounded px-2 py-1 text-sm font-mono"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        list={datalistId}
        data-testid={testId}
      />
      {datalistId && options && options.length > 0 && (
        <datalist id={datalistId}>
          {options.map((o) => (
            <option key={o} value={o} />
          ))}
        </datalist>
      )}
    </div>
  );
}
