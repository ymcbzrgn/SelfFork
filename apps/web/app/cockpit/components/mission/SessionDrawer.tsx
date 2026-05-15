/**
 * Session drawer — Mission tab — Order 6.
 *
 * Opens when a kanban card is clicked (``missionActiveCardId``). For
 * Order 6 the drawer body is a focused summary of the card; Order 7's
 * trace-tree + Order 8's chat view will mount inside it later.
 */
"use client";

import { useEffect, useState } from "react";

import { getKanban, type KanbanCardResponse } from "@/lib/api";
import { useCockpitStore } from "@/lib/store";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

export function SessionDrawer() {
  const activeCardId = useCockpitStore((s) => s.missionActiveCardId);
  const setActiveCard = useCockpitStore((s) => s.setMissionActiveCard);
  const slug = useCockpitStore((s) => s.missionActiveProjectSlug);
  const [card, setCard] = useState<KanbanCardResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (activeCardId === null || slug === null) {
      setCard(null);
      return;
    }
    void getKanban(slug)
      .then((board) => {
        if (cancelled) return;
        const cards = board.columns.flatMap(
          (c) => board.cards_by_column[c] ?? [],
        );
        setCard(cards.find((c) => c.id === activeCardId) ?? null);
      })
      .catch(() => {
        if (!cancelled) setCard(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCardId, slug]);

  return (
    <Sheet
      open={activeCardId !== null}
      onOpenChange={(open) => {
        if (!open) setActiveCard(null);
      }}
    >
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{card?.title ?? "Card"}</SheetTitle>
          <SheetDescription>
            Session: {card?.last_touched_by_session_id ?? "—"}
          </SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-3 text-sm">
          <p>
            <span className="text-muted-foreground">Status:</span>{" "}
            {card?.column ?? "—"}
          </p>
          {card?.body ? (
            <p className="whitespace-pre-wrap text-sm">{card.body}</p>
          ) : (
            <p className="text-xs text-muted-foreground">No body.</p>
          )}
          <p className="text-xs text-muted-foreground">
            Trace-tree (Order 7) and chat history (Order 8) will land
            here as those tabs ship.
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
