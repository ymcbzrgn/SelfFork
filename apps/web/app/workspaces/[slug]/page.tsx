"use client";

import { use, useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspaceHeader } from "@/components/workspace/workspace-header";
import {
  PendingConfirmationBanner,
  type PendingAction,
} from "@/components/workspace/pending-confirmation-banner";
import { KanbanBoard } from "@/components/workspace/kanban-board";
import {
  LiveRunTheater,
  type LiveRunTheaterState,
} from "@/components/workspace/live-run-theater";
import {
  ProjectNotes,
  type ProjectNote,
} from "@/components/workspace/project-notes";
import {
  approvePendingConfirmation,
  cancelPendingConfirmation,
  getProject,
  getKanban,
  getTheaterSnapshot,
  listPendingConfirmations,
  openTheaterStream,
  type PendingConfirmationResponse,
  type ProjectResponse,
  type KanbanResponse,
  type TheaterSnapshotResponse,
} from "@/lib/api";
import type { ProjectStatus } from "@/components/dashboard/project-card";

type WorkspaceTab = "kanban" | "live" | "notes" | "about";

const TAB_ORDER: WorkspaceTab[] = ["kanban", "live", "notes", "about"];

function isTab(value: string | null): value is WorkspaceTab {
  return value !== null && (TAB_ORDER as string[]).includes(value);
}

function deriveStatus(card_counts: Record<string, number>): ProjectStatus {
  const inProgress = card_counts["In Progress"] ?? 0;
  const review = card_counts["Review"] ?? 0;
  const backlog = card_counts["Backlog"] ?? 0;
  if (inProgress > 0) return "shipping";
  if (review > 0) return "pending";
  if (backlog > 0) return "sleeping";
  return "sleeping";
}

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return `${Math.max(1, Math.floor(ms / 1000))}s ago`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`;
  return `${Math.floor(ms / 86_400_000)}d ago`;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function formatTimeLeft(seconds: number): string {
  if (seconds <= 0) return "expired";
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${mins.toString().padStart(2, "0")}m left`;
  if (mins > 0) return `${mins}m left`;
  return `${seconds}s left`;
}

function pendingToBannerProp(p: PendingConfirmationResponse): PendingAction {
  return {
    id: p.id,
    command: p.command_summary,
    description: `${p.category_description} pending approval`,
    timeLeft: formatTimeLeft(p.time_left_seconds),
  };
}

function snapshotToState(s: TheaterSnapshotResponse): LiveRunTheaterState {
  return {
    active: s.active,
    cli: s.cli ?? "",
    turn: s.turn,
    durationLabel: formatDuration(s.duration_seconds),
    output: s.output.map((c) => ({ id: c.id, kind: c.kind, text: c.text })),
    screenshots: s.screenshots.map((sc) => ({
      id: sc.id,
      at: sc.at,
      thumbnailUrl: sc.thumbnail_url ?? undefined,
      previewUrl: sc.preview_url ?? undefined,
      active: sc.active,
      visionTier: sc.vision_tier,
    })),
    thoughts: s.thoughts.map((t) => ({
      id: t.id,
      summary: t.summary,
      raw: t.raw ?? undefined,
    })),
    nextPrompt: s.next_prompt ?? undefined,
  };
}

function WorkspaceContent({ slug }: { slug: string }) {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const urlTab = search.get("tab");
  const activeTab: WorkspaceTab = isTab(urlTab) ? urlTab : "kanban";

  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [kanban, setKanban] = useState<KanbanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getProject(slug).catch((e: Error) => {
        if (!cancelled) setError(e.message);
        return null;
      }),
      getKanban(slug).catch(() => null),
    ]).then(([p, k]) => {
      if (cancelled) return;
      setProject(p);
      setKanban(k);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const onTabChange = (next: string) => {
    if (!isTab(next)) return;
    const params = new URLSearchParams(search.toString());
    if (next === "kanban") {
      params.delete("tab");
    } else {
      params.set("tab", next);
    }
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  // Notes backend still pending (M6.4).
  const [notes] = useState<ProjectNote[]>([]);

  // Destructive-action pending confirmations — workspace-scoped, with
  // 30-second poll so the countdown stays fresh.
  const [pendingList, setPendingList] = useState<PendingConfirmationResponse[]>(
    [],
  );
  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      listPendingConfirmations(slug)
        .then((items) => {
          if (!cancelled) setPendingList(items);
        })
        .catch(() => {
          /* empty on error */
        });
    };
    refresh();
    const id = window.setInterval(refresh, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [slug]);

  const pending: PendingAction | null = pendingList[0]
    ? pendingToBannerProp(pendingList[0])
    : null;

  const onApprove = (id: string) => {
    approvePendingConfirmation(id)
      .then(() =>
        setPendingList((cur) => cur.filter((p) => p.id !== id)),
      )
      .catch(() => {
        /* leave list intact; banner stays visible */
      });
  };
  const onCancel = (id: string) => {
    cancelPendingConfirmation(id)
      .then(() =>
        setPendingList((cur) => cur.filter((p) => p.id !== id)),
      )
      .catch(() => {
        /* leave intact */
      });
  };
  const [theaterState, setTheaterState] =
    useState<LiveRunTheaterState | null>(null);

  // Live Run Theater wire: HTTP snapshot for initial paint, then WS
  // for live deltas. Producer events (cli.output.append / screenshot.new
  // / thought.new) land via the same envelope shape.
  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;

    getTheaterSnapshot(slug)
      .then((snap) => {
        if (cancelled) return;
        setTheaterState(snapshotToState(snap));
      })
      .catch(() => {
        if (!cancelled) setTheaterState(null);
      });

    try {
      ws = openTheaterStream(slug);
      ws.onmessage = (event) => {
        try {
          const envelope = JSON.parse(event.data) as {
            event_type: string;
            payload?: TheaterSnapshotResponse;
          };
          if (envelope.event_type === "snapshot" && envelope.payload) {
            setTheaterState(snapshotToState(envelope.payload));
          }
          // Producer event types (cli.output.append, screenshot.new,
          // thought.new) wire in during M6.5 — for now the snapshot
          // payload is the source of truth.
        } catch {
          /* swallow malformed frames */
        }
      };
      ws.onerror = () => {
        /* fall back to snapshot-only mode silently */
      };
    } catch {
      /* WS unavailable — snapshot fetch above is sufficient */
    }

    return () => {
      cancelled = true;
      if (ws && ws.readyState !== WebSocket.CLOSED) {
        ws.close();
      }
    };
  }, [slug]);

  const totalTasks = kanban
    ? Object.values(kanban.cards_by_column).reduce(
        (acc, list) => acc + list.length,
        0,
      )
    : 0;

  if (error && !project) {
    return (
      <AppShell title={slug}>
        <div className="max-w-3xl mx-auto px-gutter-desktop py-vertical-gap">
          <h1 className="font-display text-display text-on-surface">
            Workspace not found
          </h1>
          <p className="text-caption text-on-surface-variant mt-2">{error}</p>
        </div>
      </AppShell>
    );
  }

  const status = project ? deriveStatus(project.card_counts) : "sleeping";
  const doneCount = project?.card_counts?.["Done"] ?? 0;
  const totalFromProject =
    project ? Object.values(project.card_counts).reduce((a, b) => a + b, 0) : 0;
  const meta = project
    ? `${doneCount}/${totalFromProject} tasks · last activity ${relativeTime(project.updated_at)}`
    : "—";

  return (
    <AppShell title={project?.name ?? slug}>
      <div className="max-w-7xl mx-auto px-gutter-desktop py-vertical-gap flex flex-col gap-vertical-gap">
        <WorkspaceHeader
          name={project?.name ?? slug}
          status={status}
          meta={loading ? "loading…" : meta}
        />

        <PendingConfirmationBanner
          pending={pending}
          onApprove={onApprove}
          onCancel={onCancel}
        />

        <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
          <TabsList className="bg-surface-container-low border border-outline-variant/20 h-10 rounded-lg p-1">
            <TabsTrigger
              value="kanban"
              className="data-[state=active]:bg-surface data-[state=active]:text-primary data-[state=active]:shadow-sm rounded-md px-4 py-1.5 text-caption font-semibold transition-all"
            >
              Kanban
              {totalTasks > 0 && (
                <span className="ml-2 text-[10px] text-on-surface-variant tabular-nums">
                  {totalTasks}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger
              value="live"
              className="data-[state=active]:bg-surface data-[state=active]:text-primary data-[state=active]:shadow-sm rounded-md px-4 py-1.5 text-caption font-semibold transition-all flex items-center gap-1.5"
            >
              {theaterState?.active && (
                <span
                  className="w-1.5 h-1.5 rounded-full bg-error animate-pulse-red"
                  aria-hidden
                />
              )}
              Live Run
            </TabsTrigger>
            <TabsTrigger
              value="notes"
              className="data-[state=active]:bg-surface data-[state=active]:text-primary data-[state=active]:shadow-sm rounded-md px-4 py-1.5 text-caption font-semibold transition-all"
            >
              Notes
              {notes.length > 0 && (
                <span className="ml-2 text-[10px] text-on-surface-variant tabular-nums">
                  {notes.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger
              value="about"
              className="data-[state=active]:bg-surface data-[state=active]:text-primary data-[state=active]:shadow-sm rounded-md px-4 py-1.5 text-caption font-semibold transition-all"
            >
              About
            </TabsTrigger>
          </TabsList>

          <TabsContent value="kanban" className="mt-vertical-gap focus-visible:outline-none">
            <KanbanBoard
              kanban={kanban}
              loading={loading}
              totalTasks={totalTasks}
            />
          </TabsContent>

          <TabsContent value="live" className="mt-vertical-gap focus-visible:outline-none">
            <LiveRunTheater state={theaterState} />
          </TabsContent>

          <TabsContent value="notes" className="mt-vertical-gap focus-visible:outline-none">
            <ProjectNotes notes={notes} />
          </TabsContent>

          <TabsContent value="about" className="mt-vertical-gap focus-visible:outline-none">
            <section className="bg-surface rounded-xl shadow-sm border border-outline-variant/20 p-6 space-y-4">
              <h3 className="font-heading text-heading text-on-surface">
                About this workspace
              </h3>
              {project ? (
                <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 text-caption">
                  <div className="flex gap-2">
                    <dt className="text-on-surface-variant w-32">Slug:</dt>
                    <dd className="font-mono text-on-surface">{project.slug}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-on-surface-variant w-32">Created:</dt>
                    <dd className="text-on-surface tabular-nums">
                      {new Date(project.created_at).toLocaleDateString()}
                    </dd>
                  </div>
                  <div className="flex gap-2 md:col-span-2">
                    <dt className="text-on-surface-variant w-32 shrink-0">
                      Root path:
                    </dt>
                    <dd className="font-mono text-on-surface break-all">
                      {project.root_path ?? "—"}
                    </dd>
                  </div>
                  <div className="flex gap-2 md:col-span-2">
                    <dt className="text-on-surface-variant w-32 shrink-0">
                      Description:
                    </dt>
                    <dd className="text-on-surface">
                      {project.description || (
                        <span className="text-on-surface-variant/60 italic">
                          (no description)
                        </span>
                      )}
                    </dd>
                  </div>
                </dl>
              ) : (
                <p className="text-caption text-on-surface-variant">Loading…</p>
              )}
            </section>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}

export default function WorkspacePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <Suspense
      fallback={
        <AppShell title={slug}>
          <div className="max-w-7xl mx-auto px-gutter-desktop py-vertical-gap">
            <div className="h-12 bg-surface-container-low rounded animate-pulse" />
          </div>
        </AppShell>
      }
    >
      <WorkspaceContent slug={slug} />
    </Suspense>
  );
}
