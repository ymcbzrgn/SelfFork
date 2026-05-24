/**
 * Workspace Kanban — list + drag-drop + add + filter, fully wired.
 *
 * Backend (server.py:1263-1553):
 *   GET    /api/projects/{slug}/kanban          → snapshot (parent owns)
 *   POST   /api/projects/{slug}/kanban/cards    → addKanbanCard
 *   PATCH  /api/projects/{slug}/kanban/cards/{id}/move → moveKanbanCard
 *   PATCH  /api/projects/{slug}/kanban/cards/{id}      → updateKanbanCard
 *   DELETE /api/projects/{slug}/kanban/cards/{id}      → deleteKanbanCard
 *   WS     /api/projects/{slug}/kanban/stream    → real-time refresh
 *
 * The parent (workspace-client.tsx) owns the snapshot + WS subscription
 * and supplies handlers. KanbanBoard renders, runs local filter state,
 * and emits drag/drop intents — no API calls inside this file.
 */
"use client";

import { useMemo, useState } from "react";
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  closestCorners,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { Brain, Filter, Plus, Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import type { KanbanCardResponse, KanbanResponse } from "@/lib/api";

const COLUMN_ACCENT: Record<string, { label: string; isActive: boolean }> = {
  Backlog: { label: "BACKLOG", isActive: false },
  "In Progress": { label: "IN PROGRESS", isActive: true },
  Review: { label: "REVIEW", isActive: false },
  Done: { label: "DONE", isActive: false },
};

export interface KanbanBoardProps {
  kanban: KanbanResponse | null;
  loading?: boolean;
  totalTasks?: number;
  /** Open the "Add task" modal — parent owns the dialog state. */
  onAddCard?: () => void;
  /** Drag-drop finished and crossed columns. Parent does the optimistic
   * update + ``moveKanbanCard`` call + rollback on failure. */
  onCardMove?: (cardId: string, toColumn: string) => void;
}

function CardChips({ card }: { card: KanbanCardResponse }) {
  const assigned = card.last_touched_by_session_id ? "Self Jr" : null;
  return (
    <div className="flex gap-1.5 mt-3 flex-wrap">
      {assigned && (
        <span className="px-2 py-0.5 bg-surface-container text-on-surface-variant rounded text-[10px] font-bold uppercase tracking-tight">
          {assigned}
        </span>
      )}
    </div>
  );
}

interface KanbanCardViewProps {
  card: KanbanCardResponse;
  active: boolean;
  done: boolean;
  dragHandleProps?: React.HTMLAttributes<HTMLDivElement>;
  dragAttributes?: React.HTMLAttributes<HTMLDivElement>;
  isDragging?: boolean;
}

function KanbanCardView({
  card,
  active,
  done,
  dragHandleProps,
  dragAttributes,
  isDragging,
}: KanbanCardViewProps) {
  const baseClass = active
    ? "bg-surface-container-lowest p-4 rounded-xl shadow-md border-2 border-primary/20 cursor-grab active:cursor-grabbing"
    : `bg-surface-container-lowest p-4 rounded-xl shadow-sm border border-transparent hover:border-outline-variant transition-all cursor-grab active:cursor-grabbing ${done ? "opacity-60" : ""}`;
  const draggingClass = isDragging ? " ring-2 ring-primary/60 shadow-xl" : "";
  return (
    // Cards are drag-only (audit-god S7 Finding #1, 2026-05-24): an
    // ``onCardClick`` affordance with no handler wired through is a
    // UX lie. Re-introduce once the operator has a target view to
    // navigate to (edit dialog or detail surface).
    <div
      {...dragAttributes}
      {...dragHandleProps}
      className={baseClass + draggingClass}
      role="article"
      aria-label={card.title}
    >
      <span className="text-[10px] font-bold text-outline uppercase tracking-wider">
        {card.id.slice(0, 8)}
      </span>
      <h4 className="text-caption font-semibold text-on-surface mt-1">
        {card.title}
      </h4>
      {card.body && (
        <p className="text-[11px] text-on-surface-variant mt-1 line-clamp-2 whitespace-pre-wrap">
          {card.body}
        </p>
      )}
      <CardChips card={card} />
      {active && (
        <div className="mt-4 pt-3 border-t border-surface-variant flex items-center justify-between">
          <div className="flex items-center gap-1.5 bg-amber-50 text-amber-800 px-2 py-0.5 rounded-full text-[10px] font-bold ring-1 ring-amber-200">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            Self Jr · claude
          </div>
          <Brain className="h-4 w-4 text-amber-500" strokeWidth={1.75} />
        </div>
      )}
    </div>
  );
}

function DraggableKanbanCard({
  card,
  active,
  done,
}: {
  card: KanbanCardResponse;
  active: boolean;
  done: boolean;
}) {
  // useDraggable (not useSortable): the backend has no card ``order``
  // mutation endpoint, so visually reordering within a column would
  // animate then snap back — an audit-flagged UX lie (S7 Finding #2,
  // 2026-05-24). Restrict to column-to-column moves only; the column
  // drop target (``useDroppable``) catches every cross-column drop.
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: card.id,
      data: { type: "card", column: card.column },
    });

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <KanbanCardView
        card={card}
        active={active}
        done={done}
        dragAttributes={
          attributes as unknown as React.HTMLAttributes<HTMLDivElement>
        }
        dragHandleProps={
          listeners as unknown as React.HTMLAttributes<HTMLDivElement>
        }
        isDragging={isDragging}
      />
    </div>
  );
}

interface KanbanColumnProps {
  col: string;
  cards: KanbanCardResponse[];
  meta: { label: string; isActive: boolean };
  isDone: boolean;
}

function KanbanColumn({ col, cards, meta, isDone }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: `column:${col}`,
    data: { type: "column", column: col },
  });

  return (
    <div className="flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between text-caption text-on-surface-variant px-1">
        <span
          className={
            meta.isActive ? "text-primary font-bold" : "font-semibold"
          }
        >
          {meta.label} ({cards.length})
        </span>
      </div>
      <div
        ref={setNodeRef}
        className={`flex flex-col gap-2 min-h-[80px] rounded-lg transition-colors p-1 ${
          isOver ? "bg-primary/5 ring-1 ring-primary/20" : ""
        }`}
      >
        {cards.length === 0 ? (
          <div className="text-caption text-on-surface-variant/60 italic px-1 py-3">
            empty
          </div>
        ) : (
          cards.map((card) => (
            <DraggableKanbanCard
              key={card.id}
              card={card}
              active={meta.isActive}
              done={isDone}
            />
          ))
        )}
      </div>
    </div>
  );
}

function findCardById(
  kanban: KanbanResponse | null,
  id: string,
): KanbanCardResponse | undefined {
  if (!kanban) return undefined;
  for (const list of Object.values(kanban.cards_by_column)) {
    const c = list.find((card) => card.id === id);
    if (c) return c;
  }
  return undefined;
}

export function KanbanBoard({
  kanban,
  loading,
  totalTasks,
  onAddCard,
  onCardMove,
}: KanbanBoardProps) {
  const [search, setSearch] = useState("");
  const [jrOnly, setJrOnly] = useState(false);

  const columns = kanban?.columns ?? ["Backlog", "In Progress", "Review", "Done"];

  const filteredCardsByColumn = useMemo(() => {
    const out: Record<string, KanbanCardResponse[]> = {};
    const q = search.toLowerCase().trim();
    for (const col of columns) {
      const cards = kanban?.cards_by_column[col] ?? [];
      out[col] = cards.filter((card) => {
        if (jrOnly && !card.last_touched_by_session_id) return false;
        if (!q) return true;
        return (
          card.title.toLowerCase().includes(q) ||
          card.body.toLowerCase().includes(q)
        );
      });
    }
    return out;
  }, [kanban, columns, search, jrOnly]);

  // Distance activation = 5px so a stray click on a card doesn't
  // start an accidental drag. Keyboard navigation for cards is
  // deferred — useDraggable lacks the keyboard coordinate getter
  // that ``useSortable`` ships; revisit alongside the card detail
  // dialog (see ``DraggableKanbanCard`` comment).
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || !onCardMove) return;
    if (active.id === over.id) return;

    // Source column from the draggable's render-time snapshot — more
    // robust than walking ``kanban`` live, which can swap underneath a
    // mid-drag WS refetch (audit-god S7 Finding #5, 2026-05-24).
    const activeData = active.data.current as
      | { type?: string; column?: string }
      | undefined;
    const sourceColumn = activeData?.column;
    if (!sourceColumn) return;

    const overData = over.data.current as
      | { type?: string; column?: string }
      | undefined;
    let targetColumn: string;
    if (overData?.type === "column" && overData.column) {
      targetColumn = overData.column;
    } else if (overData?.type === "card" && overData.column) {
      targetColumn = overData.column;
    } else {
      return;
    }

    if (targetColumn === sourceColumn) return;
    onCardMove(active.id as string, targetColumn);
  }

  if (loading) {
    return (
      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h3 className="font-heading text-heading">Kanban</h3>
        </div>
        <div className="grid grid-cols-4 gap-4">
          {columns.map((c) => (
            <div key={c} className="space-y-3">
              <span className="text-caption text-on-surface-variant uppercase">
                {COLUMN_ACCENT[c]?.label ?? c.toUpperCase()}
              </span>
              <div className="h-24 rounded-xl bg-surface-container-low animate-pulse" />
            </div>
          ))}
        </div>
      </section>
    );
  }

  const hasFilter = Boolean(search.trim()) || jrOnly;
  const filteredTotal = Object.values(filteredCardsByColumn).reduce(
    (a, list) => a + list.length,
    0,
  );

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <h3 className="font-heading text-heading">Kanban</h3>
          <span className="text-on-surface-variant text-caption font-medium">
            {hasFilter
              ? `${filteredTotal} of ${totalTasks ?? 0} task${
                  totalTasks === 1 ? "" : "s"
                }`
              : `${totalTasks ?? 0} task${totalTasks === 1 ? "" : "s"}`}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-on-surface-variant pointer-events-none" />
            <Input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter…"
              className="pl-7 h-8 w-44 text-caption"
              aria-label="Filter Kanban tasks"
            />
          </div>
          <button
            type="button"
            onClick={() => setJrOnly((v) => !v)}
            aria-pressed={jrOnly}
            className={
              jrOnly
                ? "flex items-center gap-1 px-2.5 py-1.5 bg-primary/10 text-primary rounded-md text-caption font-semibold ring-1 ring-primary/30 transition-colors"
                : "flex items-center gap-1 px-2.5 py-1.5 text-on-surface-variant hover:bg-surface-container rounded-md text-caption font-medium transition-colors"
            }
          >
            <Filter className="h-3.5 w-3.5" strokeWidth={1.75} />
            Self Jr only
          </button>
          <button
            type="button"
            onClick={onAddCard}
            disabled={!onAddCard}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-container-high text-on-surface rounded-md text-caption font-medium hover:bg-surface-container-highest transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus className="h-4 w-4" strokeWidth={1.75} />
            Add task
          </button>
        </div>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragEnd={handleDragEnd}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {columns.map((col) => {
            const meta = COLUMN_ACCENT[col] ?? {
              label: col.toUpperCase(),
              isActive: false,
            };
            const isDone = col.toLowerCase() === "done";
            return (
              <KanbanColumn
                key={col}
                col={col}
                cards={filteredCardsByColumn[col] ?? []}
                meta={meta}
                isDone={isDone}
              />
            );
          })}
        </div>
      </DndContext>
    </section>
  );
}
