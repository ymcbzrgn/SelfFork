import { Brain, Filter, Plus } from "lucide-react";

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
  onAddTask?: () => void;
  totalTasks?: number;
}

function CardChips({ card }: { card: KanbanCardResponse }) {
  // body might contain tags — for now show a placeholder "SELF JR" if assigned
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

function KanbanCard({
  card,
  active,
  done,
}: {
  card: KanbanCardResponse;
  active: boolean;
  done: boolean;
}) {
  return (
    <div
      className={
        active
          ? "bg-surface-container-lowest p-4 rounded-xl shadow-md border-2 border-primary/20 cursor-grab"
          : `bg-surface-container-lowest p-4 rounded-xl shadow-sm border border-transparent hover:border-outline-variant transition-all cursor-grab ${
              done ? "opacity-60" : ""
            }`
      }
      role="article"
      aria-label={card.title}
    >
      <span className="text-[10px] font-bold text-outline uppercase tracking-wider">
        {card.id.slice(0, 8)}
      </span>
      <h4 className="text-caption font-semibold text-on-surface mt-1">
        {card.title}
      </h4>
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

export function KanbanBoard({ kanban, loading, onAddTask, totalTasks }: KanbanBoardProps) {
  const columns = kanban?.columns ?? ["Backlog", "In Progress", "Review", "Done"];

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

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-heading text-heading">Kanban</h3>
          <span className="text-on-surface-variant text-caption font-medium">
            {totalTasks ?? 0} task{totalTasks === 1 ? "" : "s"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label="Filter tasks"
            className="p-2 text-on-surface-variant hover:bg-surface-container rounded-md"
          >
            <Filter className="h-5 w-5" strokeWidth={1.75} />
          </button>
          <button
            type="button"
            onClick={onAddTask}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-container-high text-on-surface rounded-md text-caption font-medium hover:bg-surface-container-highest transition-colors"
          >
            <Plus className="h-4 w-4" strokeWidth={1.75} />
            Add task
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {columns.map((col) => {
          const cards = kanban?.cards_by_column[col] ?? [];
          const meta = COLUMN_ACCENT[col] ?? { label: col.toUpperCase(), isActive: false };
          const isDone = col.toLowerCase() === "done";
          return (
            <div key={col} className="flex flex-col gap-3 min-w-0">
              <div className="flex items-center justify-between text-caption text-on-surface-variant px-1">
                <span
                  className={
                    meta.isActive
                      ? "text-primary font-bold"
                      : "font-semibold"
                  }
                >
                  {meta.label} ({cards.length})
                </span>
              </div>
              <div className="flex flex-col gap-2">
                {cards.length === 0 ? (
                  <div className="text-caption text-on-surface-variant/60 italic px-1">
                    empty
                  </div>
                ) : (
                  cards.map((card) => (
                    <KanbanCard
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
        })}
      </div>
    </section>
  );
}
