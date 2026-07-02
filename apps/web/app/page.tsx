"use client";

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { QuotaGaugeCard, type QuotaCard } from "@/components/dashboard/quota-gauge-card";
import { LiveLoopStatus, type LiveLoop } from "@/components/dashboard/live-loop-status";
import { ActivityFeedItem } from "@/components/dashboard/activity-feed-item";
import {
  ProjectCard,
  NewProjectCard,
  type ProjectStatus,
} from "@/components/dashboard/project-card";
import {
  getActiveLoop,
  getActivity,
  listProjects,
  listProviders,
  listProviderUsage,
  type ActiveLoopResponse,
  type ActivityRow,
  type ProjectResponse,
  type ProviderUsage,
  type ProviderView,
} from "@/lib/api";

const ALL_PROVIDERS = ["claude", "codex", "gemini", "minimax", "glm"] as const;

// Each dashboard quota card → the on-disk auth surface (ProviderView.name)
// that proves the operator is signed in. claude/codex/gemini map 1:1;
// minimax + glm are routed through opencode ([[cli-provider-routing]]), so
// both reflect the opencode CLI's auth.
const CARD_TO_AUTH: Record<
  (typeof ALL_PROVIDERS)[number],
  ProviderView["name"]
> = {
  claude: "claude_pro",
  codex: "codex",
  gemini: "gemini",
  minimax: "opencode",
  glm: "opencode",
};

function aliasToCanonical(cli: string): (typeof ALL_PROVIDERS)[number] | null {
  if (cli === "claude-code" || cli === "claude") return "claude";
  if (cli === "codex") return "codex";
  if (cli === "gemini-cli" || cli === "gemini") return "gemini";
  if (cli === "minimax") return "minimax";
  if (cli === "glm") return "glm";
  return null;
}

function deriveResetLabel(resetAt: string | null): string | undefined {
  if (!resetAt) return undefined;
  const target = new Date(resetAt).getTime();
  const now = Date.now();
  const ms = target - now;
  if (ms <= 0) return "resetting…";
  const totalMin = Math.floor(ms / 60000);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    const remHours = hours % 24;
    return `${days}d ${remHours}h reset`;
  }
  return `${hours}h ${mins.toString().padStart(2, "0")}m left`;
}

function deriveQuotaPercent(usage: ProviderUsage): number | undefined {
  if (!usage.window_seconds || usage.window_seconds <= 0) return undefined;
  if (!usage.next_reset_at) return undefined;
  const target = new Date(usage.next_reset_at).getTime();
  const now = Date.now();
  const remainingMs = Math.max(0, target - now);
  const remainingPct = Math.min(
    100,
    Math.round((remainingMs / (usage.window_seconds * 1000)) * 100),
  );
  return remainingPct;
}

function deriveProjectStatus(card_counts: Record<string, number>): ProjectStatus {
  const inProgress = card_counts["In Progress"] ?? card_counts["in_progress"] ?? 0;
  const review = card_counts["Review"] ?? card_counts["review"] ?? 0;
  const backlog = card_counts["Backlog"] ?? card_counts["backlog"] ?? 0;
  const done = card_counts["Done"] ?? card_counts["done"] ?? 0;
  if (inProgress > 0) return "shipping";
  if (review > 0) return "pending";
  if (backlog === 0 && done === 0) return "sleeping";
  if (backlog > 0) return "sleeping";
  return "sleeping";
}

function deriveProgress(card_counts: Record<string, number>): string {
  const total = Object.values(card_counts).reduce((acc, n) => acc + (n ?? 0), 0);
  const done = card_counts["Done"] ?? card_counts["done"] ?? 0;
  if (total === 0) return "no tasks yet";
  return `${done}/${total} task${total === 1 ? "" : "s"}`;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export default function DashboardPage() {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [usage, setUsage] = useState<ProviderUsage[]>([]);
  const [providers, setProviders] = useState<ProviderView[]>([]);
  const [activeLoop, setActiveLoop] = useState<ActiveLoopResponse | null>(null);
  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listProjects().catch((e) => {
        if (!cancelled) setError(e?.message ?? "Failed to load projects");
        return [] as ProjectResponse[];
      }),
      listProviderUsage().catch(() => [] as ProviderUsage[]),
      listProviders().catch(() => [] as ProviderView[]),
      getActiveLoop().catch(() => null),
    ]).then(([p, u, pv, al]) => {
      if (cancelled) return;
      setProjects(p);
      setUsage(u);
      setProviders(pv);
      setActiveLoop(al);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // The active loop changes independently of the page lifecycle — poll
  // so the hero reflects a loop that starts or ends after page load.
  useEffect(() => {
    let cancelled = false;
    const id = window.setInterval(() => {
      getActiveLoop()
        .then((al) => {
          if (!cancelled) setActiveLoop(al);
        })
        .catch(() => {
          /* transient error — keep the last known state */
        });
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  // Recent activity feed — poll every 10s (operator pick; matches the
  // topbar bell tempo). The feed aggregates sessions + tool calls +
  // structured Q/A + heartbeat ticks + project mutations + Telegram across
  // all four CLIs; an idle system returns [] (no-mock).
  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      getActivity({ limit: 30 })
        .then((res) => {
          if (!cancelled) setActivity(res.rows);
        })
        .catch(() => {
          /* transient error — keep the last known feed */
        });
    };
    tick();
    const id = window.setInterval(tick, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const quotaCards = useMemo<QuotaCard[]>(() => {
    const byProvider = new Map<string, ProviderUsage>();
    for (const u of usage) {
      const canonical = aliasToCanonical(u.cli_agent);
      if (canonical) byProvider.set(canonical, u);
    }
    // "Signed in?" is the on-disk CLI auth status (the operator logs in
    // CLI-natively), NOT whether the provider has audit usage yet — a
    // freshly-authed CLI with no activity must still read as signed in.
    const authByName = new Map(providers.map((pv) => [pv.name, pv.status]));
    return ALL_PROVIDERS.map((provider) => {
      const authStatus = authByName.get(CARD_TO_AUTH[provider]);
      const signedIn =
        authStatus === "connected" || authStatus === "expired";
      if (!signedIn) return { provider, signedIn: false };
      // Quota gauge is still usage-derived; a signed-in provider with no
      // activity yet shows connected without a gauge (honest empty).
      const u = byProvider.get(provider);
      return {
        provider,
        signedIn: true,
        quota: u ? deriveQuotaPercent(u) : undefined,
        resetIn: u ? deriveResetLabel(u.next_reset_at) : undefined,
      };
    });
  }, [usage, providers]);

  const liveLoop: LiveLoop | null = activeLoop
    ? {
        workspace: activeLoop.workspace_name,
        workspaceSlug: activeLoop.workspace_slug,
        cli: activeLoop.cli,
        turn: activeLoop.turn,
        durationLabel: formatDuration(activeLoop.duration_seconds),
        thought:
          activeLoop.last_thought ?? "Self Jr is working on a task…",
      }
    : null;

  const subtitle = loading
    ? "Loading…"
    : `Self Jr is tracking ${projects.length} workspace${projects.length === 1 ? "" : "s"}.`;

  return (
    <AppShell title="Dashboard">
      <div className="max-w-5xl mx-auto px-gutter-desktop py-vertical-gap space-y-8">
        <section>
          <h1 className="font-display text-heading text-on-surface">Dashboard</h1>
          <p className="font-body text-on-surface-variant mt-1">{subtitle}</p>
          {error && (
            <p className="mt-2 text-caption text-error">
              {error} · Is the orchestrator running on {process.env.NEXT_PUBLIC_API_BASE_URL || "the configured API host"}?
            </p>
          )}
        </section>

        {/* Current state — the calm lead */}
        <LiveLoopStatus loop={liveLoop} />

        {/* CLI quota — quiet chip row at rest, full gauges on demand */}
        <details className="group bg-surface rounded-xl border border-outline-variant/10 p-card-padding">
          <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer flex items-center gap-3 flex-wrap">
            <span className="text-caption text-on-surface-variant">CLI quota</span>
            <span className="flex items-center gap-3 flex-wrap">
              {quotaCards.map((c) => (
                <span key={c.provider} className="inline-flex items-center gap-1.5">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      c.quota !== undefined && c.quota < 30
                        ? "bg-amber-500"
                        : c.signedIn
                          ? "bg-on-surface-variant"
                          : "bg-on-surface-variant/25"
                    }`}
                  />
                  <span className="text-[11px] text-on-surface-variant">{c.provider}</span>
                </span>
              ))}
            </span>
            <span className="ml-auto text-[11px] text-on-surface-variant/70">
              <span className="group-open:hidden">Details</span>
              <span className="hidden group-open:inline">Hide</span>
            </span>
          </summary>
          <div className="flex gap-4 flex-wrap mt-4">
            {quotaCards.map((c) => (
              <QuotaGaugeCard key={c.provider} {...c} />
            ))}
          </div>
        </details>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <section className="space-y-3">
            <h2 className="font-display text-heading text-on-surface">Recent activity</h2>
            <div className="bg-surface rounded-xl shadow-sm border border-outline-variant/10 overflow-hidden">
              {activity.length === 0 ? (
                <div className="p-card-padding text-center text-caption text-on-surface-variant">
                  Nothing yet — Self Jr will log here when a workspace is active.
                </div>
              ) : (
                <>
                  <table className="w-full text-left">
                    <tbody className="divide-y divide-outline-variant/10">
                      {activity.slice(0, 5).map((row) => (
                        <ActivityFeedItem key={row.id} row={row} />
                      ))}
                    </tbody>
                  </table>
                  {activity.length > 5 && (
                    <details className="group border-t border-outline-variant/10">
                      <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer py-3 text-center text-caption text-on-surface-variant hover:text-on-surface">
                        <span className="group-open:hidden">Show {activity.length - 5} earlier</span>
                        <span className="hidden group-open:inline">Show less</span>
                      </summary>
                      <table className="w-full text-left">
                        <tbody className="divide-y divide-outline-variant/10">
                          {activity.slice(5).map((row) => (
                            <ActivityFeedItem key={row.id} row={row} />
                          ))}
                        </tbody>
                      </table>
                    </details>
                  )}
                </>
              )}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="font-display text-heading text-on-surface">Workspaces</h2>
            <div className="bg-surface rounded-xl shadow-sm border border-outline-variant/10 overflow-hidden divide-y divide-outline-variant/10">
              {projects.map((p) => (
                <ProjectCard
                  key={p.slug}
                  slug={p.slug}
                  name={p.name}
                  status={deriveProjectStatus(p.card_counts)}
                  progress={deriveProgress(p.card_counts)}
                />
              ))}
              <NewProjectCard />
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
