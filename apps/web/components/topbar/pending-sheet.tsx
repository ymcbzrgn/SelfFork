/**
 * Pending-confirmations drawer (S8 — wires the topbar notification bell).
 *
 * The bell shows a live count; clicking it opens this drawer — a global
 * view of every destructive action awaiting operator approval (the
 * workspace banner is workspace-scoped; this is the cross-workspace one).
 * Approve / Deny here hit the same endpoints as the banner + Telegram.
 * No-mock: an empty queue shows an honest empty state.
 */
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  approvePendingConfirmation,
  cancelPendingConfirmation,
  listPendingConfirmations,
  type PendingConfirmationResponse,
} from "@/lib/api";

export function PendingSheet({
  open,
  onOpenChange,
  onResolved,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onResolved: () => void;
}) {
  const [items, setItems] = useState<PendingConfirmationResponse[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listPendingConfirmations()
      .then((rows) => setItems(rows))
      .catch(() => setItems([]));
  }, []);

  useEffect(() => {
    if (!open) return;
    setItems(null);
    refresh();
  }, [open, refresh]);

  const resolve = async (
    id: string,
    action: "approve" | "deny",
  ): Promise<void> => {
    setBusyId(id);
    try {
      if (action === "approve") {
        await approvePendingConfirmation(id);
      } else {
        await cancelPendingConfirmation(id);
      }
      refresh();
      onResolved();
    } catch {
      /* keep the row; the operator can retry */
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="bg-surface text-on-surface border-outline-variant">
        <SheetHeader>
          <SheetTitle className="text-on-surface">
            Pending confirmations
          </SheetTitle>
          <SheetDescription className="text-on-surface-variant">
            Destructive actions Self Jr is waiting on you to approve.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-2 space-y-2 overflow-y-auto">
          {items === null ? (
            <p className="py-4 text-caption text-on-surface-variant">Loading…</p>
          ) : items.length === 0 ? (
            <p className="py-4 text-caption text-on-surface-variant">
              Nothing pending. Self Jr will surface destructive actions here.
            </p>
          ) : (
            items.map((p) => (
              <div
                key={p.id}
                className="rounded-lg border border-outline-variant/40 bg-surface-container-low p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-error">
                    {p.category_id}
                  </span>
                  {p.workspace_slug && (
                    <span className="rounded bg-surface-variant px-2 py-0.5 text-[10px] font-bold uppercase text-on-surface-variant">
                      {p.workspace_slug}
                    </span>
                  )}
                </div>
                <p className="mt-1 break-words font-mono text-[11px] text-on-surface">
                  {p.command_summary}
                </p>
                <p className="mt-1 text-[11px] text-on-surface-variant">
                  {Math.max(0, Math.floor(p.time_left_seconds / 60))}m left
                </p>
                <div className="mt-2 flex justify-end gap-2">
                  <button
                    type="button"
                    disabled={busyId === p.id}
                    onClick={() => void resolve(p.id, "deny")}
                    className="rounded-md border border-outline-variant px-3 py-1 text-caption font-medium text-on-surface-variant hover:bg-surface-variant disabled:opacity-50"
                  >
                    Deny
                  </button>
                  <button
                    type="button"
                    disabled={busyId === p.id}
                    onClick={() => void resolve(p.id, "approve")}
                    className="rounded-md bg-primary px-3 py-1 text-caption font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
                  >
                    Approve
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
