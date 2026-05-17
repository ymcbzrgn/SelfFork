"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  ExternalLink,
  SendHorizontal,
  Settings as SettingsIcon,
} from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import {
  getTelegramStatus,
  listProviderUsage,
  type ProviderUsage,
  type TelegramStatusResponse,
} from "@/lib/api";

interface ProviderRow {
  canonical: "claude" | "codex" | "gemini" | "minimax" | "glm";
  displayName: string;
  subscription: string;
  pillBg: string;
  pillText: string;
}

const PROVIDERS: ProviderRow[] = [
  {
    canonical: "claude",
    displayName: "Claude Code (Anthropic Pro)",
    subscription: "Pro",
    pillBg: "bg-amber-50",
    pillText: "text-amber-700",
  },
  {
    canonical: "codex",
    displayName: "Codex (ChatGPT Plus)",
    subscription: "Plus",
    pillBg: "bg-green-50",
    pillText: "text-green-700",
  },
  {
    canonical: "gemini",
    displayName: "Gemini CLI (Google AI Studio)",
    subscription: "Free Tier",
    pillBg: "bg-blue-50",
    pillText: "text-blue-700",
  },
  {
    canonical: "minimax",
    displayName: "Minimax",
    subscription: "—",
    pillBg: "bg-violet-50",
    pillText: "text-violet-700",
  },
  {
    canonical: "glm",
    displayName: "GLM (Zhipu)",
    subscription: "—",
    pillBg: "bg-red-50",
    pillText: "text-red-700",
  },
];

function aliasToCanonical(cli: string): ProviderRow["canonical"] | null {
  if (cli === "claude-code" || cli === "claude") return "claude";
  if (cli === "codex") return "codex";
  if (cli === "gemini-cli" || cli === "gemini") return "gemini";
  if (cli === "minimax") return "minimax";
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

export default function ConnectionsPage() {
  const [usage, setUsage] = useState<ProviderUsage[]>([]);
  const [tg, setTg] = useState<TelegramStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      listProviderUsage().catch(() => [] as ProviderUsage[]),
      getTelegramStatus().catch(() => null),
    ])
      .then(([u, t]) => {
        setUsage(u);
        setTg(t);
      })
      .finally(() => setLoading(false));
  }, []);

  const tgConnected = tg?.state === "connected";

  const byCanonical = useMemo(() => {
    const map = new Map<ProviderRow["canonical"], ProviderUsage>();
    for (const u of usage) {
      const c = aliasToCanonical(u.cli_agent);
      if (c) map.set(c, u);
    }
    return map;
  }, [usage]);

  return (
    <AppShell title="Connections">
      <main className="max-w-5xl mx-auto px-gutter-desktop py-vertical-gap space-y-12">
        <section>
          <h1 className="font-display text-display text-on-surface mb-2">
            Connections
          </h1>
          <p className="font-body text-caption text-on-surface-variant">
            CLI providers + Telegram bridge + browser auth state
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
            const signedIn = !!u;
            const resetLabel = u ? deriveResetLabel(u.next_reset_at) : null;
            const dotKind: "green" | "amber" | "red" | "gray" = !signedIn
              ? "gray"
              : "green";

            return (
              <div
                key={row.canonical}
                className={`bg-surface p-5 rounded-xl shadow-sm border ${
                  signedIn
                    ? "border-outline-variant/20"
                    : "border-dashed border-outline-variant/40"
                } flex items-center gap-4 flex-wrap`}
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
                  {signedIn ? (
                    <p className="text-caption text-on-surface-variant tabular-nums">
                      Subscription: {row.subscription} ·{" "}
                      {u?.calls_in_window ?? 0} calls in {u?.window_label} ·
                      Resets in {resetLabel}
                    </p>
                  ) : (
                    <p className="text-caption text-on-surface-variant italic">
                      Not signed in
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {signedIn ? (
                    <>
                      <button
                        type="button"
                        className="px-3 py-1.5 text-on-surface-variant hover:bg-surface-container-low text-caption font-medium rounded-lg"
                      >
                        Sign out
                      </button>
                      <button
                        type="button"
                        className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg hover:bg-surface-container-low"
                      >
                        Test connection
                      </button>
                      <button
                        type="button"
                        className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg hover:bg-surface-container-low flex items-center gap-1"
                      >
                        <ExternalLink
                          className="h-3.5 w-3.5"
                          strokeWidth={1.75}
                        />
                        Browser preview
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="px-4 py-2 bg-primary text-white text-caption font-bold rounded-lg hover:bg-primary-container transition-colors flex items-center gap-1"
                    >
                      Sign in
                      <ArrowRight className="h-4 w-4" strokeWidth={1.75} />
                    </button>
                  )}
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
              {!tgConnected && (
                <button
                  type="button"
                  className="px-4 py-2 bg-primary text-white text-caption font-bold rounded-lg hover:bg-primary-container transition-colors flex items-center gap-1"
                >
                  Connect
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} />
                </button>
              )}
            </div>
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2 text-caption">
              <div className="flex gap-2">
                <dt className="text-on-surface-variant w-32">Bot:</dt>
                <dd className="font-mono text-on-surface">
                  {tg?.bot_username ? `@${tg.bot_username}` : "—"}
                </dd>
              </div>
              <div className="flex gap-2">
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
                <dd className="text-on-surface-variant/60 italic">
                  {tg?.last_activity_summary ?? "never"}
                </dd>
              </div>
            </dl>
            <div className="mt-4 pt-4 border-t border-outline-variant/30 flex items-center gap-2 flex-wrap">
              <button
                type="button"
                disabled
                className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg flex items-center gap-1 text-on-surface-variant opacity-50 cursor-not-allowed"
              >
                <SendHorizontal className="h-3.5 w-3.5" strokeWidth={1.75} />
                Send test
              </button>
              <button
                type="button"
                disabled
                className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg opacity-50 cursor-not-allowed"
              >
                View log
              </button>
              <button
                type="button"
                disabled
                className="px-3 py-1.5 text-on-surface-variant text-caption font-medium rounded-lg flex items-center gap-1 opacity-50 cursor-not-allowed"
              >
                <SettingsIcon className="h-3.5 w-3.5" strokeWidth={1.75} />
                Bot settings
              </button>
            </div>
          </div>
          <p className="text-caption text-on-surface-variant flex items-center gap-1">
            <Check className="h-3.5 w-3.5 text-success" strokeWidth={2} />
            Soft confirmation (4h, fail-safe NO) replaces autonomy sliders — see
            ADR-006 §4.5.
          </p>
        </section>
      </main>
    </AppShell>
  );
}
