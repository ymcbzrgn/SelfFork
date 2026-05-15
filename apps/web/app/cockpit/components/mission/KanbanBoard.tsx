/**
 * Mission tab kanban board — Order 6.
 *
 * Linear-style swimlane kanban. Status lives on the *column* axis
 * (backlog / in_progress / review / done with handed-off rendered as
 * a banner inside ``in_progress``). The orchestrator's tool calls
 * push status changes via the WS subscription; the operator only
 * has one manual lever — the **Resume** CTA on a paused/handed-off
 * card (Order 6 §M-3 read-mostly contract).
 *
 * Drag-drop is intentionally NOT wired in this Order — only the
 * SwimlaneToggle, drawer trigger, and Resume CTA. Free drag-drop
 * is M5+ (memory: ``project_provider_usage_source`` mantığı —
 * state derived, not mutated).
 */
"use client";

import { Badge } from "@/components/ui/badge";
import type { KanbanCardResponse, KanbanResponse } from "@/lib/api";
import { useCockpitStore } from "@/lib/store";

import { HandoffLane } from "./HandoffLane";
import { SwimlaneToggle } from "./SwimlaneToggle";

const COLUMN_LABEL: Record<string, string> = {
  backlog: "Backlog",
  in_progress: "In progress",
  review: "Review",
  done: "Done",
};

interface Props {
  slug: string;
  board: KanbanResponse;
}

export function KanbanBoard({ slug, board }: Props) {
  const swimlaneMode = useCockpitStore((s) => s.missionSwimlaneMode);
  void slug;

  const columns = board.columns;
  const cardsByColumn = board.cards_by_column;

  if (swimlaneMode === "session") {
    return <SessionSwimlaneView board={board} />;
  }

  return (
    <section
      className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4"
      aria-label="Mission kanban (status mode)"
      data-testid="mission-kanban-status"
    >
      <div className="md:col-span-2 xl:col-span-4 flex items-center justify-between">
        <h3 className="text-base font-semibold tracking-tight">
          Mission board
        </h3>
        <SwimlaneToggle />
      </div>
      {columns.map((col) => (
        <Column
          key={col}
          column={col}
          cards={cardsByColumn[col] ?? []}
        />
      ))}
      <HandoffLane board={board} />
    </section>
  );
}

function SessionSwimlaneView({ board }: { board: KanbanResponse }) {
  // Group cards by ``last_touched_by_session_id``. Cards with no
  // touched-by are pooled under "Unassigned" so the layout stays
  // stable across reloads.
  const cards = board.columns.flatMap((c) => board.cards_by_column[c] ?? []);
  const grouped = new Map<string, KanbanCardResponse[]>();
  for (const card of cards) {
    const key = card.last_touched_by_session_id ?? "Unassigned";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(card);
  }
  return (
    <section
      className="space-y-4"
      aria-label="Mission kanban (session mode)"
      data-testid="mission-kanban-session"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold tracking-tight">
          Mission board (by session)
        </h3>
        <SwimlaneToggle />
      </div>
      {[...grouped.entries()].map(([sessionKey, sessionCards]) => (
        <SessionLane
          key={sessionKey}
          sessionKey={sessionKey}
          cards={sessionCards}
        />
      ))}
    </section>
  );
}

function Column({
  column,
  cards,
}: {
  column: string;
  cards: KanbanCardResponse[];
}) {
  return (
    <div
      className="flex min-h-[16rem] flex-col gap-2 rounded-xl border border-border/60 bg-card/40 p-3"
      data-testid={`mission-column-${column}`}
    >
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium uppercase text-muted-foreground">
          {COLUMN_LABEL[column] ?? column}
        </span>
        <Badge variant="outline" className="font-mono text-[10px]">
          {cards.length}
        </Badge>
      </div>
      {cards.length === 0 ? (
        <p className="text-xs text-muted-foreground">No cards.</p>
      ) : (
        cards.map((card) => <CardRow key={card.id} card={card} />)
      )}
    </div>
  );
}

function SessionLane({
  sessionKey,
  cards,
}: {
  sessionKey: string;
  cards: KanbanCardResponse[];
}) {
  return (
    <div
      className="rounded-xl border border-border/60 bg-card/40 p-3"
      data-testid={`mission-lane-${sessionKey}`}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-xs text-muted-foreground">
          {sessionKey}
        </span>
        <Badge variant="outline" className="font-mono text-[10px]">
          {cards.length}
        </Badge>
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {cards.map((card) => (
          <CardRow key={card.id} card={card} />
        ))}
      </div>
    </div>
  );
}

function CardRow({ card }: { card: KanbanCardResponse }) {
  const setActiveCard = useCockpitStore((s) => s.setMissionActiveCard);
  return (
    <button
      type="button"
      onClick={() => setActiveCard(card.id)}
      className="rounded-md border border-border/40 bg-background p-2 text-left text-sm transition-colors hover:border-foreground/40"
      data-testid={`mission-card-${card.id}`}
    >
      <p className="font-medium">{card.title}</p>
      {card.body ? (
        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
          {card.body}
        </p>
      ) : null}
    </button>
  );
}
