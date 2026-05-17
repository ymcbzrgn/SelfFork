"use client";

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { QuotaGaugeCard, type QuotaCard } from "@/components/dashboard/quota-gauge-card";
import { LiveLoopStatus, type LiveLoop } from "@/components/dashboard/live-loop-status";
import {
  ActivityFeedItem,
  type ActivityRow,
} from "@/components/dashboard/activity-feed-item";
import {
  ProjectCard,
  NewProjectCard,
  type ProjectStatus,
} from "@/components/dashboard/project-card";
import {
  getActiveLoop,
  listProjects,
  listProviderUsage,
  type ActiveLoopResponse,
  type ProjectResponse,
  type ProviderUsage,
} from "@/lib/api";

const ALL_PROVIDERS = ["claude", "codex", "gemini", "minimax", "glm"] as const;

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
  const [activeLoop, setActiveLoop] = useState<ActiveLoopResponse | null>(null);
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
      getActiveLoop().catch(() => null),
    ]).then(([p, u, al]) => {
      if (cancelled) return;
      setProjects(p);
      setUsage(u);
      setActiveLoop(al);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const quotaCards = useMemo<QuotaCard[]>(() => {
    const byProvider = new Map<string, ProviderUsage>();
    for (const u of usage) {
      const canonical = aliasToCanonical(u.cli_agent);
      if (canonical) byProvider.set(canonical, u);
    }
    return ALL_PROVIDERS.map((provider) => {
      const u = byProvider.get(provider);
      if (!u) return { provider, signedIn: false };
      return {
        provider,
        signedIn: true,
        quota: deriveQuotaPercent(u),
        resetIn: deriveResetLabel(u.next_reset_at),
      };
    });
  }, [usage]);

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
  // Activity backend not wired yet; show empty state.
  const activity: ActivityRow[] = [];

  const subtitle = loading
    ? "Loading…"
    : `Self Jr is tracking ${projects.length} workspace${projects.length === 1 ? "" : "s"}.`;

  return (
    <AppShell title="Dashboard">
      <div className="max-w-7xl mx-auto px-gutter-desktop py-vertical-gap space-y-8">
        <section>
          <h1 className="font-display text-display text-on-surface">Dashboard</h1>
          <p className="font-body text-on-surface-variant mt-1">{subtitle}</p>
          {error && (
            <p className="mt-2 text-caption text-error">
              {error} · Is the orchestrator running on {process.env.NEXT_PUBLIC_API_BASE_URL || "the configured API host"}?
            </p>
          )}
        </section>

        <section className="space-y-4">
          <h2 className="font-display text-heading text-on-surface">CLI Quota</h2>
          <div className="flex gap-4 flex-wrap">
            {quotaCards.map((c) => (
              <QuotaGaugeCard key={c.provider} {...c} />
            ))}
          </div>
        </section>

        <LiveLoopStatus loop={liveLoop} />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <section className="space-y-4">
            <h2 className="font-display text-heading text-on-surface">Recent activity</h2>
            <div className="bg-surface rounded-xl shadow-sm border border-outline-variant/10 overflow-hidden">
              {activity.length === 0 ? (
                <div className="p-card-padding text-center text-caption text-on-surface-variant">
                  No activity yet. Self Jr will start logging when a workspace is active.
                </div>
              ) : (
                <table className="w-full text-left">
                  <tbody className="divide-y divide-outline-variant/10">
                    {activity.map((row) => (
                      <ActivityFeedItem key={row.id} row={row} />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>

          <section className="space-y-4">
            <h2 className="font-display text-heading text-on-surface">Workspaces</h2>
            <div className="grid grid-cols-2 gap-4">
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
