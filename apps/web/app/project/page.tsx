/**
 * Project detail — header + provider usage strip + kanban board + sessions.
 *
 * Reads the slug from a URL search param (``?slug=<slug>``) so the
 * route is statically exportable.
 *
 * The kanban board subscribes to ``/api/projects/<slug>/kanban/stream``
 * (WebSocket), polling falls back to 5s only if the WS dies. Drag-drop
 * across columns uses @dnd-kit; moves are optimistic — the UI updates
 * locally first, the server is updated next, the WS push reconciles.
 */
"use client";

import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ArrowLeft, FileText, Folder, GripVertical, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { CardDetailPanel } from "@/components/card-detail-panel";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/empty";
import { ErrorState } from "@/components/error-state";
import { RelativeAge } from "@/components/format";
import { AppShell } from "@/components/layout/app-shell";
import { ProviderUsageStrip } from "@/components/provider-usage-strip";
import { StatusPill, type ColumnState } from "@/components/status-pill";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  addKanbanCard,
  deleteKanbanCard,
  getKanban,
  getProject,
  moveKanbanCard,
  openKanbanStream,
  type KanbanCardResponse,
  type KanbanResponse,
  type ProjectResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const COLUMN_ORDER: ColumnState[] = ["backlog", "in_progress", "review", "done"];

const COLUMN_LABEL: Record<string, string> = {
  backlog: "Backlog",
  in_progress: "In progress",
  review: "Review",
  done: "Done",
};

export default function ProjectDetailPage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Project">
          <Skeleton className="h-32 w-full" />
        </AppShell>
      }
    >
      <ProjectDetail />
    </Suspense>
  );
}

function ProjectDetail() {
  const params = useSearchParams();
  const slug = params.get("slug");

  if (!slug) {
    return (
      <AppShell title="Project">
        <ErrorState
          title="Missing slug"
          detail="Open this page from /projects/ so the URL carries ?slug=..."
        />
      </AppShell>
    );
  }

  return (
    <AppShell title={`Project · ${slug}`}>
      <ProjectBody slug={slug} />
    </AppShell>
  );
}

function ProjectBody({ slug }: { slug: string }) {
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [board, setBoard] = useState<KanbanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [focusedCardId, setFocusedCardId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, k] = await Promise.all([getProject(slug), getKanban(slug)]);
      setProject(p);
      setBoard(k);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [slug]);

  useEffect(() => {
    if (!slug) {
      return;
    }
    void refresh();
    const ws = openKanbanStream(slug);
    ws.addEventListener("message", (e) => {
      try {
        setBoard(JSON.parse(e.data) as KanbanResponse);
      } catch {
        /* ignore malformed payload */
      }
    });
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    const startPolling = () => {
      pollTimer ??= setInterval(() => void refresh(), 5_000);
    };
    ws.addEventListener("close", startPolling);
    ws.addEventListener("error", startPolling);
    return () => {
      ws.close();
      if (pollTimer !== null) {
        clearInterval(pollTimer);
      }
    };
  }, [refresh, slug]);

  // Optimistic move: rewrite ``board`` locally, fire API, let WS / refetch
  // converge. Reverts on error by triggering refresh().
  const onMove = useCallback(
    async (cardId: string, from: string, to: string) => {
      if (from === to) return;
      setBoard((prev) => (prev ? optimisticMove(prev, cardId, from, to) : prev));
      try {
        await moveKanbanCard(slug, cardId, to);
      } catch {
        // Server rejected — refetch to revert.
        void refresh();
      }
    },
    [slug, refresh],
  );

  const onDelete = useCallback(
    async (cardId: string) => {
      // Optimistic remove + close detail panel.
      setBoard((prev) => (prev ? optimisticRemove(prev, cardId) : prev));
      setSelectedCardId((prev) => (prev === cardId ? null : prev));
      try {
        await deleteKanbanCard(slug, cardId);
      } catch {
        void refresh();
      }
    },
    [slug, refresh],
  );

  // Flat card list ordered by column, used for J/K navigation.
  const orderedCards = useMemo(() => {
    if (!board) return [] as KanbanCardResponse[];
    return board.columns.flatMap((c) => board.cards_by_column[c] ?? []);
  }, [board]);

  // Keyboard navigation: J/K to step focus, Enter to open the focused
  // card, Esc to clear focus / close the detail panel. Skip when a
  // text input has focus or a modal is open above us (cmdk handles
  // its own keys).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) {
        return;
      }
      // Only react when the project body owns the keyboard — i.e. the
      // detail panel and command palette aren't open. (CmdK and panel
      // each have their own Esc handlers; we just don't compete.)
      if (selectedCardId !== null && e.key !== "j" && e.key !== "k") return;

      if (e.key === "j" || e.key === "k") {
        if (orderedCards.length === 0) return;
        e.preventDefault();
        setFocusedCardId((prev) => {
          const idx = prev ? orderedCards.findIndex((c) => c.id === prev) : -1;
          const delta = e.key === "j" ? 1 : -1;
          const next = idx === -1 ? 0 : (idx + delta + orderedCards.length) % orderedCards.length;
          return orderedCards[next].id;
        });
      } else if (e.key === "Enter" && focusedCardId) {
        e.preventDefault();
        setSelectedCardId(focusedCardId);
      } else if (e.key === "Escape" && focusedCardId) {
        e.preventDefault();
        setFocusedCardId(null);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [orderedCards, focusedCardId, selectedCardId]);

  const selectedCard =
    selectedCardId && board
      ? orderedCards.find((c) => c.id === selectedCardId) ?? null
      : null;

  if (error && project === null) {
    return (
      <ErrorState title="Couldn't load project" detail={error} />
    );
  }
  if (project === null || board === null) {
    return <KanbanBoardSkeleton />;
  }

  return (
    <div className="space-y-6">
      <ProjectHeader project={project} />
      <section className="space-y-3">
        <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Provider usage
        </h3>
        <ProviderUsageStrip />
      </section>
      <KanbanBoard
        slug={slug}
        board={board}
        focusedCardId={focusedCardId}
        onMove={onMove}
        onChanged={() => void refresh()}
        onOpenCard={(id) => setSelectedCardId(id)}
        onFocusCard={(id) => setFocusedCardId(id)}
      />
      <CardDetailPanel
        card={selectedCard}
        onClose={() => setSelectedCardId(null)}
        onDelete={onDelete}
      />
    </div>
  );
}

function ProjectHeader({ project }: { project: ProjectResponse }) {
  return (
    <div className="space-y-3">
      <Link
        href="/projects/"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
      >
        <ArrowLeft className="h-3 w-3" />
        All projects
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Folder className="h-5 w-5 text-muted-foreground" />
            {project.name}
          </h2>
          <p className="font-mono text-xs text-muted-foreground">
            slug: {project.slug}
            {project.root_path ? (
              <>
                {" "}· root: <span title={project.root_path}>{project.root_path}</span>
              </>
            ) : null}
          </p>
          {project.description ? (
            <p className="max-w-3xl text-sm text-muted-foreground">
              {project.description}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-1 text-[11px] text-muted-foreground">
          <span>
            updated <RelativeAge isoTs={project.updated_at} />
          </span>
          <span>
            created <RelativeAge isoTs={project.created_at} />
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Kanban ────────────────────────────────────────────────────────────────

interface KanbanBoardProps {
  slug: string;
  board: KanbanResponse;
  focusedCardId: string | null;
  onMove: (cardId: string, from: string, to: string) => Promise<void>;
  onChanged: () => void;
  onOpenCard: (cardId: string) => void;
  onFocusCard: (cardId: string | null) => void;
}

function KanbanBoard({
  slug,
  board,
  focusedCardId,
  onMove,
  onChanged,
  onOpenCard,
  onFocusCard,
}: KanbanBoardProps) {
  const [activeCard, setActiveCard] = useState<KanbanCardResponse | null>(null);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
    useSensor(KeyboardSensor),
  );

  // Index cards by id once for O(1) drag-overlay lookup.
  const cardsById = useMemo(() => {
    const m = new Map<string, { card: KanbanCardResponse; column: string }>();
    for (const col of board.columns) {
      for (const c of board.cards_by_column[col] ?? []) {
        m.set(c.id, { card: c, column: col });
      }
    }
    return m;
  }, [board]);

  const onDragStart = (e: DragStartEvent) => {
    const entry = cardsById.get(e.active.id as string);
    if (entry) setActiveCard(entry.card);
  };

  const onDragEnd = (e: DragEndEvent) => {
    setActiveCard(null);
    const { active, over } = e;
    if (!over) return;
    const cardId = active.id as string;
    const entry = cardsById.get(cardId);
    if (!entry) return;
    const targetColumn = over.id as string;
    if (!COLUMN_ORDER.includes(targetColumn as ColumnState)) return;
    void onMove(cardId, entry.column, targetColumn);
  };

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight">Kanban</h3>
          <p className="text-xs text-muted-foreground">
            Drag cards between columns. Jr's tool calls (
            <code className="font-mono">kanban_card_done</code>,
            <code className="font-mono">kanban_card_move</code>) update this
            board live over WebSocket.
          </p>
        </div>
      </div>
      <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {board.columns.map((col) => (
            <Column
              key={col}
              slug={slug}
              column={col}
              cards={board.cards_by_column[col] ?? []}
              focusedCardId={focusedCardId}
              onChanged={onChanged}
              onOpenCard={onOpenCard}
              onFocusCard={onFocusCard}
            />
          ))}
        </div>
        <DragOverlay>
          {activeCard ? <KanbanCardSurface card={activeCard} dragging overlay /> : null}
        </DragOverlay>
      </DndContext>
    </section>
  );
}

function KanbanBoardSkeleton() {
  return (
    <section className="space-y-3">
      <Skeleton className="h-6 w-24" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="flex min-h-[16rem] flex-col gap-2 rounded-xl border border-border bg-card/50 p-3"
          >
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ))}
      </div>
    </section>
  );
}

function Column({
  slug,
  column,
  cards,
  focusedCardId,
  onChanged,
  onOpenCard,
  onFocusCard,
}: {
  slug: string;
  column: string;
  cards: KanbanCardResponse[];
  focusedCardId: string | null;
  onChanged: () => void;
  onOpenCard: (cardId: string) => void;
  onFocusCard: (cardId: string | null) => void;
}) {
  const [adding, setAdding] = useState(false);
  const { setNodeRef, isOver } = useDroppable({ id: column });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex min-h-[16rem] flex-col rounded-xl border bg-card/40 p-3 transition-colors",
        isOver
          ? "border-primary/50 bg-primary/5"
          : "border-border/60",
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <StatusPill state={column} />
        </div>
        <Badge variant="outline" className="font-mono text-[10px]">
          {cards.length}
        </Badge>
      </div>

      <div className="flex flex-1 flex-col gap-2">
        {cards.length === 0 ? (
          <Empty variant="compact">
            <EmptyHeader>
              <EmptyTitle>{COLUMN_LABEL[column] ?? column}</EmptyTitle>
              <EmptyDescription>No cards yet.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          cards.map((card) => (
            <KanbanCard
              key={card.id}
              slug={slug}
              card={card}
              focused={focusedCardId === card.id}
              onChanged={onChanged}
              onOpen={() => onOpenCard(card.id)}
              onFocus={() => onFocusCard(card.id)}
            />
          ))
        )}
      </div>

      {column === "backlog" ? (
        adding ? (
          <AddCardForm
            slug={slug}
            onCancel={() => setAdding(false)}
            onAdded={() => {
              setAdding(false);
              onChanged();
            }}
          />
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="mt-2 inline-flex items-center justify-center gap-1 rounded-md border border-dashed border-border/60 px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
          >
            <Plus className="h-3 w-3" />
            Add card
          </button>
        )
      ) : null}
    </div>
  );
}

function AddCardForm({
  slug,
  onCancel,
  onAdded,
}: {
  slug: string;
  onCancel: () => void;
  onAdded: () => void;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addKanbanCard(slug, { title: title.trim(), body: body.trim() });
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="mt-2 space-y-2 rounded-lg border border-border bg-background p-2">
      <input
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Card title"
        className="w-full rounded border border-input bg-background px-2 py-1 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Optional details…"
        rows={2}
        className="w-full rounded border border-input bg-background px-2 py-1 text-[11px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
      />
      {error ? <p className="text-[11px] text-destructive">{error}</p> : null}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="text-[11px] text-muted-foreground hover:text-foreground"
        >
          Cancel
        </button>
        <Button size="sm" type="submit" disabled={busy}>
          <Plus className="h-3 w-3" />
          {busy ? "Adding…" : "Add"}
        </Button>
      </div>
    </form>
  );
}

interface KanbanCardProps {
  slug: string;
  card: KanbanCardResponse;
  focused: boolean;
  onChanged: () => void;
  onOpen: () => void;
  onFocus: () => void;
}

function KanbanCard({ slug, card, focused, onChanged, onOpen, onFocus }: KanbanCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useSortable({ id: card.id });

  const style = transform
    ? { transform: CSS.Translate.toString(transform) }
    : undefined;

  const remove = async () => {
    try {
      await deleteKanbanCard(slug, card.id);
      onChanged();
    } catch {
      // ignore — banner-level error UI not needed for one-shot deletes
    }
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <KanbanCardSurface
        card={card}
        listeners={listeners}
        dragging={isDragging}
        focused={focused}
        onDelete={remove}
        onOpen={onOpen}
        onFocus={onFocus}
      />
    </div>
  );
}

function KanbanCardSurface({
  card,
  listeners,
  dragging = false,
  overlay = false,
  focused = false,
  onDelete,
  onOpen,
  onFocus,
}: {
  card: KanbanCardResponse;
  listeners?: ReturnType<typeof useSortable>["listeners"];
  dragging?: boolean;
  overlay?: boolean;
  focused?: boolean;
  onDelete?: () => void;
  onOpen?: () => void;
  onFocus?: () => void;
}) {
  return (
    <div
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onClick={onOpen}
      onMouseEnter={onFocus}
      onKeyDown={(e) => {
        if (!onOpen) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className={cn(
        "group relative cursor-pointer rounded-lg border bg-card text-xs shadow-sm transition-[box-shadow,transform,border-color] duration-150",
        "border-border hover:border-foreground/30 hover:shadow-md",
        focused && !overlay && "border-primary/60 ring-2 ring-primary/30",
        dragging && !overlay && "opacity-30 ring-2 ring-border",
        overlay && "ring-2 ring-primary shadow-2xl",
      )}
    >
      <div className="flex items-start gap-1 px-3 py-2.5">
        {listeners ? (
          <button
            type="button"
            {...listeners}
            aria-label="Drag card"
            onClick={(e) => e.stopPropagation()}
            className="-ml-1 mt-0.5 cursor-grab touch-none rounded p-0.5 text-muted-foreground/50 transition-colors hover:bg-accent hover:text-foreground active:cursor-grabbing"
          >
            <GripVertical className="h-3.5 w-3.5" />
          </button>
        ) : (
          <span className="-ml-1 mt-0.5 p-0.5 text-muted-foreground/50">
            <GripVertical className="h-3.5 w-3.5" />
          </span>
        )}
        <p className="flex-1 break-words font-medium leading-snug text-foreground">
          {card.title}
        </p>
        {onDelete ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            title="Delete card"
            className="opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        ) : null}
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-border/50 bg-muted/20 px-3 py-1.5 text-[10px] text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <FileText className="h-3 w-3" />
          <span className="font-mono">{card.id.slice(-6)}</span>
        </div>
        <span className="font-mono">
          <RelativeAge isoTs={card.updated_at} />
        </span>
      </div>
    </div>
  );
}

// ── helpers ───────────────────────────────────────────────────────────────

function optimisticMove(
  board: KanbanResponse,
  cardId: string,
  from: string,
  to: string,
): KanbanResponse {
  const next: KanbanResponse = {
    ...board,
    cards_by_column: { ...board.cards_by_column },
  };
  const fromCards = next.cards_by_column[from] ?? [];
  const idx = fromCards.findIndex((c) => c.id === cardId);
  if (idx < 0) return board;
  const [moved] = fromCards.splice(idx, 1);
  next.cards_by_column[from] = [...fromCards];
  const movedUpdated: KanbanCardResponse = {
    ...moved,
    column: to,
    updated_at: new Date().toISOString(),
  };
  next.cards_by_column[to] = [...(next.cards_by_column[to] ?? []), movedUpdated];
  return next;
}

function optimisticRemove(
  board: KanbanResponse,
  cardId: string,
): KanbanResponse {
  const next: KanbanResponse = {
    ...board,
    cards_by_column: { ...board.cards_by_column },
  };
  for (const col of board.columns) {
    const cards = next.cards_by_column[col] ?? [];
    if (cards.some((c) => c.id === cardId)) {
      next.cards_by_column[col] = cards.filter((c) => c.id !== cardId);
    }
  }
  return next;
}
