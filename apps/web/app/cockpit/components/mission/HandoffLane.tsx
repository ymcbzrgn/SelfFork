/**
 * Handoff lane — Mission tab — Order 6.
 *
 * "Handed-off" isn't a kanban column on its own; it's a derived view
 * of cards that the orchestrator marked ``last_touched_by_session_id``
 * AND status=``in_progress`` for sessions that have since paused. The
 * cockpit surfaces them as a separate banner so the operator sees the
 * Resume CTA without hunting columns.
 */
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { KanbanResponse } from "@/lib/api";
import { resumePausedSession } from "@/lib/queries/mission-queries";

interface Props {
  board: KanbanResponse;
}

export function HandoffLane({ board }: Props) {
  // Heuristic: cards touched by a session that's still ``in_progress``
  // on the board are candidates. The dashboard already separates
  // paused sessions via ``/api/sessions/paused``; pulling them in
  // here would couple the kanban WS to the paused REST endpoint —
  // we surface the candidate set instead and let the operator click.
  const candidates = (board.cards_by_column.in_progress ?? []).filter(
    (card) => card.last_touched_by_session_id !== null,
  );
  if (candidates.length === 0) return null;
  return (
    <div
      className="md:col-span-2 xl:col-span-4 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3"
      data-testid="mission-handoff-lane"
    >
      <h4 className="text-sm font-medium text-amber-200">
        Handed-off cards
      </h4>
      <p className="mt-1 text-xs text-amber-100/70">
        Sessions that touched these cards may be paused. Resume to
        continue.
      </p>
      <ul className="mt-2 space-y-2">
        {candidates.map((card) => (
          <li
            key={card.id}
            className="flex items-center justify-between gap-3 text-sm"
          >
            <span>
              <span className="font-medium">{card.title}</span>{" "}
              <span className="font-mono text-[11px] text-amber-100/70">
                ← {card.last_touched_by_session_id}
              </span>
            </span>
            <ResumeButton sessionId={card.last_touched_by_session_id!} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ResumeButton({ sessionId }: { sessionId: string }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const onClick = async () => {
    setPending(true);
    setError(null);
    try {
      await resumePausedSession(sessionId);
    } catch (e) {
      // Order 6 audit fix: previously the catch silently swallowed —
      // operator clicked Resume on a non-paused session and got no
      // feedback. Now the inline status surfaces the failure.
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };
  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        type="button"
        onClick={onClick}
        variant="outline"
        disabled={pending}
        data-testid={`mission-resume-${sessionId}`}
      >
        {pending ? "Resuming…" : "Resume"}
      </Button>
      {error ? (
        <span className="text-[10px] text-rose-300">{error}</span>
      ) : null}
    </div>
  );
}
