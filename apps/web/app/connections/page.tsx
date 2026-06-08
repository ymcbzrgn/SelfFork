"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Terminal, X } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import {
  getTelegramActivity,
  getTelegramSettings,
  getTelegramStatus,
  listProviders,
  listProviderUsage,
  sendTelegramTest,
  setupTelegram,
  type ProviderUsage,
  type ProviderView,
  type TelegramActivityResponse,
  type TelegramConfig,
  type TelegramStatusResponse,
} from "@/lib/api";

interface ProviderRow {
  canonical: "claude" | "codex" | "gemini" | "minimax" | "glm" | "opencode";
  registryName: ProviderView["name"] | null;
  displayName: string;
  loginCommand: string;
  pillBg: string;
  pillText: string;
}

// Canonical CLI rows the Connections page renders. Each row is anchored
// to a (a) usage-aggregator alias for the live quota numbers, (b) optional
// ``ProviderRegistry`` name for the auth-expired badge. Subscription tier
// labels are intentionally absent — S4-S8 no-mock rule: every value on
// screen is either fetched from the backend or removed.
const PROVIDERS: ProviderRow[] = [
  {
    canonical: "claude",
    registryName: "claude_pro",
    displayName: "Claude Code (Anthropic)",
    loginCommand: "claude /login",
    pillBg: "bg-amber-50",
    pillText: "text-amber-700",
  },
  {
    canonical: "codex",
    registryName: "codex",
    displayName: "Codex (ChatGPT / OpenAI)",
    loginCommand: "codex login",
    pillBg: "bg-green-50",
    pillText: "text-green-700",
  },
  {
    canonical: "gemini",
    registryName: "gemini",
    displayName: "Gemini CLI (Google)",
    loginCommand: "gemini auth login",
    pillBg: "bg-blue-50",
    pillText: "text-blue-700",
  },
  {
    canonical: "opencode",
    registryName: "opencode",
    displayName: "OpenCode (rotational provider)",
    loginCommand: "opencode auth login",
    pillBg: "bg-purple-50",
    pillText: "text-purple-700",
  },
  {
    canonical: "minimax",
    registryName: "mmx",
    displayName: "Minimax",
    loginCommand: "minimax-cli login",
    pillBg: "bg-violet-50",
    pillText: "text-violet-700",
  },
  {
    canonical: "glm",
    registryName: null,
    displayName: "GLM (Zhipu)",
    loginCommand: "glm login",
    pillBg: "bg-red-50",
    pillText: "text-red-700",
  },
];

function aliasToCanonical(cli: string): ProviderRow["canonical"] | null {
  if (cli === "claude-code" || cli === "claude") return "claude";
  if (cli === "codex") return "codex";
  if (cli === "gemini-cli" || cli === "gemini") return "gemini";
  if (cli === "opencode") return "opencode";
  if (cli === "minimax-cli" || cli === "minimax") return "minimax";
  if (cli === "glm") return "glm";
  return null;
}

function deriveResetLabel(resetAt: string | null): string {
  if (!resetAt) return "—";
  const ms = new Date(resetAt).getTime() - Date.now();
  if (ms <= 0) return "resetting now";
  const totalMin = Math.floor(ms / 60000);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours >= 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
  return `${hours}h ${mins.toString().padStart(2, "0")}m`;
}

function StatusDot({ kind }: { kind: "green" | "amber" | "red" | "gray" }) {
  const cls =
    kind === "green"
      ? "bg-success"
      : kind === "amber"
        ? "bg-amber-500"
        : kind === "red"
          ? "bg-error"
          : "bg-on-surface-variant/40";
  return <span className={`w-2.5 h-2.5 rounded-full ${cls}`} aria-hidden />;
}

interface TelegramSetupFormState {
  bot_token: string;
  chat_id: string;
  mode: "polling" | "webhook";
  webhook_url: string;
  webhook_secret: string;
  soft_confirm_window_hours: number;
}

function emptySetupState(prefill?: TelegramConfig | null): TelegramSetupFormState {
  return {
    bot_token: prefill?.bot_token ?? "",
    chat_id: prefill?.chat_id ?? "",
    mode: prefill?.mode ?? "polling",
    webhook_url: prefill?.webhook_url ?? "",
    webhook_secret: prefill?.webhook_secret ?? "",
    soft_confirm_window_hours: prefill?.soft_confirm_window_hours ?? 4,
  };
}

export default function ConnectionsPage() {
  const [usage, setUsage] = useState<ProviderUsage[]>([]);
  const [providers, setProviders] = useState<ProviderView[]>([]);
  const [tg, setTg] = useState<TelegramStatusResponse | null>(null);
  const [tgSettings, setTgSettings] = useState<TelegramConfig | null>(null);
  const [activity, setActivity] = useState<TelegramActivityResponse | null>(
    null,
  );
  const [testStatus, setTestStatus] = useState<
    "idle" | "sending" | "ok" | "error"
  >("idle");
  const [testError, setTestError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupOpen, setSetupOpen] = useState(false);
  const [setupForm, setSetupForm] = useState<TelegramSetupFormState>(
    emptySetupState(),
  );
  const [setupBusy, setSetupBusy] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [u, p, t, ts, a] = await Promise.all([
      listProviderUsage().catch(() => [] as ProviderUsage[]),
      listProviders().catch(() => [] as ProviderView[]),
      getTelegramStatus().catch(() => null),
      getTelegramSettings().catch(() => null),
      getTelegramActivity().catch(
        () => ({ inbound: [], outbound: [] }) as TelegramActivityResponse,
      ),
    ]);
    setUsage(u);
    setProviders(p);
    setTg(t);
    setTgSettings(ts);
    setActivity(a);
  }, []);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  const tgConnected = tg?.state === "connected";

  const byCanonical = useMemo(() => {
    const map = new Map<ProviderRow["canonical"], ProviderUsage>();
    for (const u of usage) {
      const c = aliasToCanonical(u.cli_agent);
      if (c) map.set(c, u);
    }
    return map;
  }, [usage]);

  const registryByName = useMemo(() => {
    const map = new Map<ProviderView["name"], ProviderView>();
    for (const p of providers) map.set(p.name, p);
    return map;
  }, [providers]);

  const openSetup = useCallback(() => {
    setSetupForm(emptySetupState(tgSettings));
    setSetupError(null);
    setSetupOpen(true);
  }, [tgSettings]);

  const submitSetup = useCallback(async () => {
    setSetupBusy(true);
    setSetupError(null);
    try {
      await setupTelegram({
        bot_token: setupForm.bot_token,
        chat_id: setupForm.chat_id || undefined,
        mode: setupForm.mode,
        webhook_url: setupForm.webhook_url || undefined,
        webhook_secret: setupForm.webhook_secret || undefined,
        soft_confirm_window_hours: setupForm.soft_confirm_window_hours,
      });
      setSetupOpen(false);
      await refresh();
    } catch (err) {
      setSetupError(err instanceof Error ? err.message : "setup failed");
    } finally {
      setSetupBusy(false);
    }
  }, [setupForm, refresh]);

  return (
    <AppShell title="Connections">
      <main className="max-w-5xl mx-auto px-gutter-desktop py-vertical-gap space-y-12">
        <section>
          <h1 className="font-display text-display text-on-surface mb-2">
            Connections
          </h1>
          <p className="font-body text-caption text-on-surface-variant">
            CLI provider auth status + Telegram bridge. SelfFork
            doesn't orchestrate sign-in — each CLI handles its own
            auth in your terminal.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-[11px] uppercase tracking-wider font-bold text-on-surface-variant">
            CLI Providers
          </h2>
          {loading && (
            <p className="text-caption text-on-surface-variant">Loading…</p>
          )}
          {PROVIDERS.map((row) => {
            const u = byCanonical.get(row.canonical);
            const reg = row.registryName
              ? registryByName.get(row.registryName)
              : undefined;
            const hasUsage = !!u;
            const expired = !!(reg?.last_error?.startsWith("auth_expired:"));
            const dotKind: "green" | "amber" | "red" | "gray" = expired
              ? "red"
              : hasUsage
                ? "green"
                : "gray";
            const resetLabel = u ? deriveResetLabel(u.next_reset_at) : null;

            return (
              <div
                key={row.canonical}
                className={`bg-surface p-5 rounded-xl shadow-sm border ${
                  hasUsage
                    ? "border-outline-variant/20"
                    : "border-dashed border-outline-variant/40"
                } flex items-start gap-4 flex-wrap`}
              >
                <div className="flex items-center gap-3">
                  <StatusDot kind={dotKind} />
                  <span
                    className={`${row.pillBg} ${row.pillText} text-[10px] font-bold uppercase tracking-tight px-2 py-0.5 rounded`}
                  >
                    {row.canonical}
                  </span>
                </div>
                <div className="flex-1 min-w-[260px]">
                  <h3 className="text-body font-semibold text-on-surface">
                    {row.displayName}
                  </h3>
                  {hasUsage && !expired && (
                    <p className="text-caption text-on-surface-variant tabular-nums">
                      {u?.calls_in_window ?? 0} calls in {u?.window_label}
                      {resetLabel && ` · Resets in ${resetLabel}`}
                    </p>
                  )}
                  {!hasUsage && !expired && (
                    row.canonical === "minimax" || row.canonical === "glm" ? (
                      <p className="text-caption text-on-surface-variant italic">
                        Routed via OpenCode — Self Jr reaches this
                        provider through the OpenCode CLI, so its quota
                        rolls up under OpenCode above.
                      </p>
                    ) : (
                      <p className="text-caption text-on-surface-variant italic">
                        No recent activity. Run{" "}
                        <code className="font-mono text-on-surface bg-surface-container-low px-1.5 rounded">
                          {row.loginCommand}
                        </code>{" "}
                        in your terminal to sign in.
                      </p>
                    )
                  )}
                  {expired && (
                    <p className="text-caption text-error">
                      Auth expired — Self Jr will keep nudging you in
                      Telegram. Run{" "}
                      <code className="font-mono bg-error/10 px-1.5 rounded">
                        {row.loginCommand}
                      </code>{" "}
                      to re-authenticate.
                    </p>
                  )}
                  {u?.proactive_source && (
                    <p
                      className="text-[11px] text-on-surface-variant/70 mt-1"
                      title="Where the live secondary quota signal comes from"
                    >
                      Source:{" "}
                      <span className="font-mono">{u.proactive_source}</span>
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 text-caption text-on-surface-variant">
                  <Terminal className="h-3.5 w-3.5" strokeWidth={1.75} />
                  <span className="font-mono">
                    {row.canonical === "minimax" || row.canonical === "glm"
                      ? "via opencode"
                      : row.loginCommand}
                  </span>
                </div>
              </div>
            );
          })}
        </section>

        <section className="space-y-3">
          <h2 className="text-[11px] uppercase tracking-wider font-bold text-on-surface-variant">
            Telegram Bridge
          </h2>
          <div className="bg-surface p-6 rounded-xl shadow-sm border border-outline-variant/20">
            <div className="flex items-start justify-between flex-wrap gap-3 mb-4">
              <div className="flex items-center gap-3">
                <StatusDot kind={tgConnected ? "green" : "gray"} />
                <h3 className="text-body font-bold text-on-surface">
                  Telegram Bridge —{" "}
                  {tgConnected ? "Connected" : "Not configured"}
                </h3>
              </div>
              <button
                type="button"
                onClick={openSetup}
                className="px-4 py-2 bg-primary text-white text-caption font-bold rounded-lg hover:bg-primary-container transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                {tgConnected ? "Reconfigure…" : "Connect"}
              </button>
            </div>
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2 text-caption">
              <div className="flex gap-2">
                <dt className="text-on-surface-variant w-32">Bot:</dt>
                <dd className="font-mono text-on-surface">
                  {tg?.bot_username ? `@${tg.bot_username}` : "—"}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-on-surface-variant w-32">Mode:</dt>
                <dd className="font-mono text-on-surface">
                  {tg?.mode ?? "—"}
                </dd>
              </div>
              <div className="flex gap-2 md:col-span-2">
                <dt className="text-on-surface-variant w-32">Webhook:</dt>
                <dd className="font-mono text-on-surface break-all">
                  {tg?.webhook_url ?? (
                    <span className="text-on-surface-variant/60 italic">
                      not set
                    </span>
                  )}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-on-surface-variant w-32">Soft confirm:</dt>
                <dd className="text-on-surface">
                  {tg?.soft_confirm_window_hours ?? 4} hours
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-on-surface-variant w-32">Last activity:</dt>
                <dd className="text-on-surface">
                  {tg?.last_activity_summary ?? (
                    <span className="text-on-surface-variant/60 italic">
                      never
                    </span>
                  )}
                </dd>
              </div>
            </dl>
            <div className="mt-4 pt-4 border-t border-outline-variant/30 flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => {
                  void (async () => {
                    setTestStatus("sending");
                    try {
                      await sendTelegramTest();
                      setTestStatus("ok");
                      const fresh = await getTelegramActivity();
                      setActivity(fresh);
                    } catch (err) {
                      setTestStatus("error");
                      setTestError(
                        err instanceof Error
                          ? err.message
                          : "test message failed",
                      );
                    }
                  })();
                }}
                disabled={!tgConnected || testStatus === "sending"}
                className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg flex items-center gap-1 text-on-surface enabled:hover:bg-surface-container disabled:text-on-surface-variant disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                {testStatus === "sending" ? "Sending…" : "Send test"}
              </button>
              {testStatus === "ok" && (
                <span className="text-caption text-success">✓ delivered</span>
              )}
              {testStatus === "error" && (
                <span className="text-caption text-error">
                  ✗ {testError ?? "failed"}
                </span>
              )}
            </div>
            {activity &&
              activity.inbound.length + activity.outbound.length > 0 && (
                <div className="mt-4 pt-4 border-t border-outline-variant/30">
                  <h4 className="text-[11px] uppercase tracking-wider font-bold text-on-surface-variant mb-2">
                    Recent activity
                  </h4>
                  <ul className="space-y-1 text-caption">
                    {[
                      ...activity.outbound.slice(0, 3),
                      ...activity.inbound.slice(0, 3),
                    ]
                      .sort((a, b) => b.at.localeCompare(a.at))
                      .slice(0, 5)
                      .map((entry) => (
                        <li
                          key={`${entry.direction}-${entry.at}`}
                          className="flex items-center gap-2"
                        >
                          <span
                            className={
                              entry.direction === "outbound"
                                ? "text-primary"
                                : "text-success"
                            }
                          >
                            {entry.direction === "outbound" ? "↑" : "↓"}
                          </span>
                          <span className="text-on-surface-variant w-32 truncate">
                            {new Date(entry.at).toLocaleTimeString()}
                          </span>
                          <span className="text-on-surface truncate">
                            {entry.summary}
                          </span>
                        </li>
                      ))}
                  </ul>
                </div>
              )}
          </div>
          <p className="text-caption text-on-surface-variant flex items-center gap-1">
            <Check className="h-3.5 w-3.5 text-success" strokeWidth={2} />
            Soft confirmation (4h, fail-safe NO) replaces autonomy sliders — see
            ADR-006 §4.5.
          </p>
        </section>
      </main>

      {setupOpen && (
        <TelegramSetupModal
          form={setupForm}
          onChange={setSetupForm}
          onCancel={() => setSetupOpen(false)}
          onSubmit={() => void submitSetup()}
          busy={setupBusy}
          error={setupError}
        />
      )}
    </AppShell>
  );
}

function TelegramSetupModal({
  form,
  onChange,
  onCancel,
  onSubmit,
  busy,
  error,
}: {
  form: TelegramSetupFormState;
  onChange: (next: TelegramSetupFormState) => void;
  onCancel: () => void;
  onSubmit: () => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-surface max-w-lg w-full rounded-xl shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-outline-variant/30">
          <h3 className="font-heading text-heading text-on-surface">
            Connect Telegram bridge
          </h3>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            title="Close"
            className="text-on-surface-variant hover:text-on-surface rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <X className="h-5 w-5" strokeWidth={1.75} />
          </button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <label className="block">
            <span className="text-caption font-semibold text-on-surface block mb-1.5">
              Bot token (from @BotFather)
            </span>
            <input
              type="password"
              value={form.bot_token}
              onChange={(e) =>
                onChange({ ...form, bot_token: e.target.value })
              }
              placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
              className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </label>
          <label className="block">
            <span className="text-caption font-semibold text-on-surface block mb-1.5">
              Chat ID (optional, falls back to allowlist file)
            </span>
            <input
              type="text"
              value={form.chat_id}
              onChange={(e) => onChange({ ...form, chat_id: e.target.value })}
              placeholder="123456789"
              className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </label>
          <div>
            <span className="text-caption font-semibold text-on-surface block mb-1.5">
              Mode
            </span>
            <div className="flex gap-4 text-caption">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={form.mode === "polling"}
                  onChange={() => onChange({ ...form, mode: "polling" })}
                  className="w-4 h-4 accent-primary"
                />
                <span>Polling (operator laptop)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  checked={form.mode === "webhook"}
                  onChange={() => onChange({ ...form, mode: "webhook" })}
                  className="w-4 h-4 accent-primary"
                />
                <span>Webhook (server self-host)</span>
              </label>
            </div>
          </div>
          {form.mode === "webhook" && (
            <>
              <label className="block">
                <span className="text-caption font-semibold text-on-surface block mb-1.5">
                  Public webhook URL (HTTPS, required)
                </span>
                <input
                  type="url"
                  value={form.webhook_url}
                  onChange={(e) =>
                    onChange({ ...form, webhook_url: e.target.value })
                  }
                  placeholder="https://selffork.example.com/api/telegram/webhook"
                  className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </label>
              <label className="block">
                <span className="text-caption font-semibold text-on-surface block mb-1.5">
                  Webhook secret token (recommended)
                </span>
                <input
                  type="password"
                  value={form.webhook_secret}
                  onChange={(e) =>
                    onChange({ ...form, webhook_secret: e.target.value })
                  }
                  className="w-full font-mono text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </label>
            </>
          )}
          <label className="block">
            <span className="text-caption font-semibold text-on-surface block mb-1.5">
              Soft confirm window (hours, 1–72)
            </span>
            <input
              type="number"
              min={1}
              max={72}
              value={form.soft_confirm_window_hours}
              onChange={(e) =>
                onChange({
                  ...form,
                  soft_confirm_window_hours:
                    Number(e.target.value) ||
                    form.soft_confirm_window_hours,
                })
              }
              className="w-full text-caption px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg tabular-nums focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </label>
          {error && (
            <p className="text-caption text-error pt-2 break-all">{error}</p>
          )}
        </div>
        <div className="px-6 py-4 border-t border-outline-variant/30 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || !form.bot_token.trim()}
            onClick={onSubmit}
            className="px-4 py-2 bg-primary text-white text-caption font-bold rounded-lg disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            {busy ? "Saving…" : "Save & connect"}
          </button>
        </div>
      </div>
    </div>
  );
}
