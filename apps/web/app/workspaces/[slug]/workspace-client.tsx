"use client";

import { useEffect, useRef, useState, Suspense } from "react";
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
import { CliSwitchDialog } from "@/components/workspace/cli-switch-dialog";
import { ProjectNotes } from "@/components/workspace/project-notes";
import { AddKanbanCardDialog } from "@/components/workspace/add-kanban-card-dialog";
import { EditProjectDialog } from "@/components/workspace/edit-project-dialog";
import { SessionTranscriptDrawer } from "@/components/workspace/session-transcript-drawer";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  ApiError,
  approvePendingConfirmation,
  archiveProject,
  cancelPendingConfirmation,
  createMindNote,
  deleteMindNote,
  extendPendingConfirmation,
  getActiveLoop,
  getProject,
  getKanban,
  getTheaterSnapshot,
  listMindNotes,
  listPendingConfirmations,
  moveKanbanCard,
  openKanbanStream,
  openTheaterStream,
  pauseWorkspaceAutopilot,
  resumeWorkspaceAutopilot,
  unarchiveProject,
  updateMindNote,
  type KanbanCardResponse,
  type NoteResponse,
  type PendingConfirmationResponse,
  type ProjectResponse,
  type KanbanResponse,
  type TheaterSnapshotResponse,
  type TheaterCLIOutputChunk,
  type TheaterThoughtResponse,
} from "@/lib/api";
import type { ProjectStatus } from "@/components/dashboard/project-card";

type WorkspaceTab = "kanban" | "live" | "notes" | "about";

const TAB_ORDER: WorkspaceTab[] = ["kanban", "live", "notes", "about"];

function isTab(value: string | null): value is WorkspaceTab {
  return value !== null && (TAB_ORDER as string[]).includes(value);
}

function deriveStatus(card_counts: Record<string, number>): ProjectStatus {
  // Backend ships lowercase column ids (model.py:38-43,
  // ``DEFAULT_COLUMNS``). Audit-god S7 Finding #2 (2026-05-24) caught
  // this surface reading the human-facing labels and silently
  // defaulting every workspace to "sleeping".
  const inProgress = card_counts["in_progress"] ?? 0;
  const review = card_counts["review"] ?? 0;
  const backlog = card_counts["backlog"] ?? 0;
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

  // Notes — Mind T2 Episodic per-project (S7, ADR-007 §4 S7).
  // Fetched on mount; mutations (add/title/content/delete) optimistically
  // update local state then persist via mind_router endpoints. The
  // backend supersede pattern means each save creates a new id; the
  // optimistic write therefore replaces both id and updated_at.
  const [notes, setNotes] = useState<NoteResponse[]>([]);
  const [notesLoading, setNotesLoading] = useState(true);
  const [savingNote, setSavingNote] = useState(false);
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setNotesLoading(true);
    listMindNotes(slug, "episodic", 200)
      .then((rows) => {
        if (cancelled) return;
        setNotes(rows);
        setNotesLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setNotes([]);
        setNotesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const handleAddNote = async () => {
    try {
      setSavingNote(true);
      const created = await createMindNote(slug, {
        content: "# Untitled\n\nWrite your decision or learning here.",
        intent: "Untitled",
        tier: "episodic",
        kind: "decision",
      });
      setNotes((prev) => [created, ...prev]);
      setSelectedNoteId(created.id);
    } catch (e) {
      console.error("createMindNote failed", e);
    } finally {
      setSavingNote(false);
    }
  };

  // Debounced PATCH — coalesce keystroke bursts into one supersede.
  // ``debounceTimers`` keyed by id so editing the title while content
  // debounces still fires the right patch.
  const noteDebounceTimers = useRef<Map<string, number>>(new Map());
  const noteLatestPatch = useRef<
    Map<string, { intent?: string; content?: string }>
  >(new Map());

  const scheduleNotePatch = (id: string) => {
    const existing = noteDebounceTimers.current.get(id);
    if (existing !== undefined) window.clearTimeout(existing);
    const handle = window.setTimeout(() => {
      void flushNotePatch(id);
    }, 800);
    noteDebounceTimers.current.set(id, handle);
  };

  const flushNotePatch = async (id: string) => {
    const patch = noteLatestPatch.current.get(id);
    if (patch === undefined) return;
    noteLatestPatch.current.delete(id);
    noteDebounceTimers.current.delete(id);
    setSavingNote(true);
    try {
      const updated = await updateMindNote(slug, id, patch);
      // Supersede replaces id; remap selection + replace in list.
      setNotes((prev) => prev.map((n) => (n.id === id ? updated : n)));
      setSelectedNoteId((cur) => (cur === id ? updated.id : cur));
    } catch (e) {
      console.error("updateMindNote failed", e);
    } finally {
      setSavingNote(false);
    }
  };

  const handleNoteTitleChange = (id: string, intent: string) => {
    // Optimistic UI: reflect the typed value immediately.
    setNotes((prev) =>
      prev.map((n) => (n.id === id ? { ...n, intent } : n)),
    );
    const current = noteLatestPatch.current.get(id) ?? {};
    noteLatestPatch.current.set(id, { ...current, intent });
    scheduleNotePatch(id);
  };

  const handleNoteContentChange = (id: string, content: string) => {
    setNotes((prev) =>
      prev.map((n) => (n.id === id ? { ...n, content } : n)),
    );
    const current = noteLatestPatch.current.get(id) ?? {};
    noteLatestPatch.current.set(id, { ...current, content });
    scheduleNotePatch(id);
  };

  const handleNoteDelete = async (id: string) => {
    // Flush any pending edits so we don't supersede after delete.
    const pendingTimer = noteDebounceTimers.current.get(id);
    if (pendingTimer !== undefined) {
      window.clearTimeout(pendingTimer);
      noteDebounceTimers.current.delete(id);
    }
    noteLatestPatch.current.delete(id);
    try {
      await deleteMindNote(slug, id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
      setSelectedNoteId((cur) => (cur === id ? null : cur));
    } catch (e) {
      console.error("deleteMindNote failed", e);
    }
  };

  // Audit-god S7 Finding #3 (2026-05-24) — clear pending debounce
  // timers + latest-patch entries on unmount so route changes don't
  // leak a setState on an unmounted component or fire a stale PATCH
  // race after the operator navigates away.
  useEffect(() => {
    const timers = noteDebounceTimers.current;
    const patches = noteLatestPatch.current;
    return () => {
      for (const timer of timers.values()) {
        window.clearTimeout(timer);
      }
      timers.clear();
      patches.clear();
    };
  }, []);

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
  const onExtend = (id: string, hours: number) => {
    extendPendingConfirmation(id, hours)
      .then((updated) =>
        setPendingList((cur) =>
          cur.map((p) => (p.id === updated.id ? updated : p)),
        ),
      )
      .catch(() => {
        /* leave intact */
      });
  };
  const [theaterState, setTheaterState] =
    useState<LiveRunTheaterState | null>(null);
  const [switchOpen, setSwitchOpen] = useState(false);
  const [addKanbanOpen, setAddKanbanOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [archiveConfirmOpen, setArchiveConfirmOpen] = useState(false);
  const [pausingAutopilot, setPausingAutopilot] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [headerError, setHeaderError] = useState<string | null>(null);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [transcriptSessionId, setTranscriptSessionId] = useState<
    string | null
  >(null);

  const handleOpenTranscript = async () => {
    setTranscriptOpen(true);
    // Lazy-fetch the active loop's session_id only when the operator
    // actually asks for the transcript. If the active loop belongs to
    // a different workspace, surface "no active session" inside the
    // drawer rather than the wrong session's events.
    try {
      const loop = await getActiveLoop();
      if (loop && loop.workspace_slug === slug) {
        setTranscriptSessionId(loop.session_id);
      } else {
        setTranscriptSessionId(null);
      }
    } catch {
      setTranscriptSessionId(null);
    }
  };

  const handlePauseToggle = async () => {
    if (project === null || pausingAutopilot) return;
    setPausingAutopilot(true);
    setHeaderError(null);
    try {
      const updated = project.autopilot_paused
        ? await resumeWorkspaceAutopilot(slug)
        : await pauseWorkspaceAutopilot(slug);
      setProject(updated);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setHeaderError(`Pause toggle failed: ${msg}`);
    } finally {
      setPausingAutopilot(false);
    }
  };

  const handleArchiveConfirm = async () => {
    if (project === null || archiving) return;
    setArchiving(true);
    setHeaderError(null);
    try {
      const wasArchived = project.archived_at !== null;
      const updated = wasArchived
        ? await unarchiveProject(slug)
        : await archiveProject(slug);
      setProject(updated);
      setArchiveConfirmOpen(false);
      // On archive, send the operator back to the projects list — the
      // sidebar's default listing will no longer show this slug.
      if (!wasArchived) {
        router.push("/");
      }
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setHeaderError(`Archive toggle failed: ${msg}`);
    } finally {
      setArchiving(false);
    }
  };

  const handleSwitchWorkspace = (target: string) => {
    if (target === slug) return;
    router.push(`/workspaces/${target}`);
  };

  const handleProjectSaved = (updated: ProjectResponse) => {
    setProject(updated);
  };

  // S8 — the topbar title dropdown dispatches these events for the active
  // workspace; route them to the same handlers the header buttons use. The
  // pause handler closes over `project`, so we read it through a ref kept
  // current each render (the [] effect must not capture a stale closure).
  const pauseRef = useRef(handlePauseToggle);
  pauseRef.current = handlePauseToggle;
  useEffect(() => {
    const openSwitch = () => setSwitchOpen(true);
    const openEdit = () => setEditOpen(true);
    const togglePause = () => void pauseRef.current();
    const openArchive = () => setArchiveConfirmOpen(true);
    window.addEventListener("selffork:workspace:switch", openSwitch);
    window.addEventListener("selffork:workspace:edit", openEdit);
    window.addEventListener("selffork:workspace:pause", togglePause);
    window.addEventListener("selffork:workspace:archive", openArchive);
    return () => {
      window.removeEventListener("selffork:workspace:switch", openSwitch);
      window.removeEventListener("selffork:workspace:edit", openEdit);
      window.removeEventListener("selffork:workspace:pause", togglePause);
      window.removeEventListener("selffork:workspace:archive", openArchive);
    };
  }, []);

  // Kanban WS — backend emits on every mutation (server.py:1529). We
  // debounce 150ms so a burst of card.* events coalesces into one
  // refetch. The optimistic update inside `handleCardMove` keeps the
  // UI responsive; the WS refetch is the authoritative reconcile.
  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;
    let refreshTimer: number | null = null;

    const triggerRefresh = () => {
      if (cancelled) return;
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => {
        getKanban(slug)
          .then((k) => {
            if (!cancelled) setKanban(k);
          })
          .catch(() => {
            /* keep last-known state on refetch failure */
          });
      }, 150);
    };

    try {
      ws = openKanbanStream(slug);
      ws.onmessage = triggerRefresh;
      ws.onerror = () => {
        /* keep snapshot-only mode silently */
      };
    } catch {
      /* WS unavailable — initial fetch in mount effect is enough */
    }

    return () => {
      cancelled = true;
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
      if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
    };
  }, [slug]);

  // Drag-drop → optimistic local mutation + persist; rollback by
  // refetch on failure. The successful path's WS event will also
  // re-affirm the new state.
  const handleCardMove = (cardId: string, toColumn: string) => {
    setKanban((prev) => {
      if (!prev) return prev;
      let moved: KanbanCardResponse | undefined;
      const next: Record<string, KanbanCardResponse[]> = {};
      for (const [col, list] of Object.entries(prev.cards_by_column)) {
        const idx = list.findIndex((c) => c.id === cardId);
        if (idx >= 0) {
          moved = list[idx];
          next[col] = [...list.slice(0, idx), ...list.slice(idx + 1)];
        } else {
          next[col] = list;
        }
      }
      if (!moved) return prev;
      const updated: KanbanCardResponse = { ...moved, column: toColumn };
      next[toColumn] = [...(next[toColumn] ?? []), updated];
      return { ...prev, cards_by_column: next };
    });
    moveKanbanCard(slug, cardId, toColumn).catch(() => {
      // Rollback via fresh fetch — backend is source of truth.
      getKanban(slug)
        .then((k) => setKanban(k))
        .catch(() => {
          /* leave state intact */
        });
    });
  };

  const handleCardAdded = (card: KanbanCardResponse) => {
    setKanban((prev) => {
      if (!prev) return prev;
      const next = { ...prev.cards_by_column };
      // Append to match backend insertion order (audit-god S7 Finding
      // #3, 2026-05-24). The WS-debounced refetch returns the
      // authoritative snapshot ~150ms later; prepending here causes
      // a visible jump when the refetch reconciles.
      next[card.column] = [...(next[card.column] ?? []), card];
      return { ...prev, cards_by_column: next };
    });
  };

  // Live Run Theater wire: HTTP snapshot for initial paint, then WS
  // for live deltas. Producer events (cli.output.append / screenshot.new
  // / thought.new) land via the same envelope shape.
  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;

    getTheaterSnapshot(slug)
      .then((snap) => {
        if (cancelled) return;
        // Initial paint only — once the WS sets state (snapshot or a
        // live delta) it is authoritative; a late HTTP response must
        // not clobber deltas already appended.
        setTheaterState((prev) =>
          prev === null ? snapshotToState(snap) : prev,
        );
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
            payload?: unknown;
          };
          if (envelope.event_type === "snapshot" && envelope.payload) {
            setTheaterState(
              snapshotToState(envelope.payload as TheaterSnapshotResponse),
            );
          } else if (
            envelope.event_type === "cli.output.append" &&
            envelope.payload
          ) {
            const c = envelope.payload as TheaterCLIOutputChunk;
            setTheaterState((prev) =>
              prev
                ? {
                    ...prev,
                    output: [
                      ...prev.output,
                      { id: c.id, kind: c.kind, text: c.text },
                    ],
                  }
                : prev,
            );
          } else if (
            envelope.event_type === "thought.new" &&
            envelope.payload
          ) {
            const t = envelope.payload as TheaterThoughtResponse;
            setTheaterState((prev) =>
              prev
                ? {
                    ...prev,
                    thoughts: [
                      ...prev.thoughts,
                      {
                        id: t.id,
                        summary: t.summary,
                        raw: t.raw ?? undefined,
                      },
                    ],
                  }
                : prev,
            );
          }
          // screenshot.new has no S2 producer (ADR-007 §4 S2 scope) —
          // the screenshot pane stays an honest empty state.
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
  // Lowercase backend key — see ``deriveStatus`` comment.
  const doneCount = project?.card_counts?.["done"] ?? 0;
  const totalFromProject =
    project ? Object.values(project.card_counts).reduce((a, b) => a + b, 0) : 0;
  const meta = project
    ? `${doneCount}/${totalFromProject} tasks · last activity ${relativeTime(project.updated_at)}`
    : "—";

  return (
    <AppShell title={project?.name ?? slug}>
      <div className="max-w-7xl mx-auto px-gutter-desktop py-vertical-gap flex flex-col gap-vertical-gap">
        <WorkspaceHeader
          slug={slug}
          name={project?.name ?? slug}
          status={status}
          meta={loading ? "loading…" : meta}
          autopilotPaused={project?.autopilot_paused ?? false}
          archived={project?.archived_at !== null && project?.archived_at !== undefined}
          onPauseToggle={() => void handlePauseToggle()}
          pausing={pausingAutopilot}
          onEdit={() => setEditOpen(true)}
          onArchiveToggle={() => setArchiveConfirmOpen(true)}
          archiving={archiving}
          onSwitchWorkspace={handleSwitchWorkspace}
        />

        {headerError && (
          <p
            role="alert"
            className="text-caption text-error-foreground bg-error-container/30 border border-error/30 rounded-md px-3 py-2"
          >
            {headerError}
          </p>
        )}

        <PendingConfirmationBanner
          pending={pending}
          onApprove={onApprove}
          onCancel={onCancel}
          onExtend={onExtend}
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
              onAddCard={() => setAddKanbanOpen(true)}
              onCardMove={handleCardMove}
            />
          </TabsContent>

          <TabsContent value="live" className="mt-vertical-gap focus-visible:outline-none">
            <LiveRunTheater
              state={theaterState}
              onSwitchCli={() => setSwitchOpen(true)}
              onPause={() => void handlePauseToggle()}
              onOpenTranscript={() => void handleOpenTranscript()}
            />
          </TabsContent>

          <TabsContent value="notes" className="mt-vertical-gap focus-visible:outline-none">
            <ProjectNotes
              notes={notes}
              loading={notesLoading}
              saving={savingNote}
              selectedId={selectedNoteId}
              onSelect={setSelectedNoteId}
              onAdd={() => void handleAddNote()}
              onTitleChange={handleNoteTitleChange}
              onContentChange={handleNoteContentChange}
              onDelete={(id) => void handleNoteDelete(id)}
            />
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

        <CliSwitchDialog
          slug={slug}
          open={switchOpen}
          onOpenChange={setSwitchOpen}
        />

        <AddKanbanCardDialog
          slug={slug}
          open={addKanbanOpen}
          onOpenChange={setAddKanbanOpen}
          columns={kanban?.columns ?? ["Backlog", "In Progress", "Review", "Done"]}
          onAdded={handleCardAdded}
        />

        <EditProjectDialog
          project={project}
          open={editOpen}
          onOpenChange={setEditOpen}
          onSaved={handleProjectSaved}
        />

        <SessionTranscriptDrawer
          sessionId={transcriptSessionId}
          open={transcriptOpen}
          onOpenChange={setTranscriptOpen}
          workspaceName={project?.name ?? slug}
        />

        <AlertDialog
          open={archiveConfirmOpen}
          onOpenChange={(next) => {
            if (archiving) return;
            setArchiveConfirmOpen(next);
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {project?.archived_at !== null && project?.archived_at !== undefined
                  ? "Unarchive this workspace?"
                  : "Archive this workspace?"}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {project?.archived_at !== null && project?.archived_at !== undefined
                  ? "Restores the workspace to the active sidebar listing and makes it Heartbeat-eligible again."
                  : "Hides the workspace from the sidebar (Self Jr won't pick it up). Reversible via the Unarchive button — your files and audit history stay on disk."}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={archiving}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  void handleArchiveConfirm();
                }}
                disabled={archiving}
              >
                {archiving
                  ? "Working…"
                  : project?.archived_at !== null && project?.archived_at !== undefined
                    ? "Unarchive"
                    : "Archive"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </AppShell>
  );
}

export function WorkspaceClient({ slug }: { slug: string }) {
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
