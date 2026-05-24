/**
 * Session transcript drawer — S7 (ADR-007 §4 S7).
 *
 * In-place right-slide Sheet (operator's AskUserQuestion 2026-05-24
 * pick: "in-place Sheet drawer"). Reads ``GET /api/sessions/{id}/events``
 * and renders the chronological audit log with category + payload for
 * each entry. Lazy-fetched on open so an idle theater never pays the
 * audit-read cost.
 */
"use client";

import { useEffect, useState } from "react";
import { FileText } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ApiError,
  getSessionEvents,
  type AuditEvent,
} from "@/lib/api";

function errMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

const LEVEL_TONE: Record<string, string> = {
  ERROR: "text-error",
  WARNING: "text-amber-700",
  INFO: "text-on-surface-variant",
  DEBUG: "text-on-surface-variant/60",
};

export interface SessionTranscriptDrawerProps {
  sessionId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceName: string;
}

export function SessionTranscriptDrawer({
  sessionId,
  open,
  onOpenChange,
  workspaceName,
}: SessionTranscriptDrawerProps) {
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || sessionId === null) {
      setEvents(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setEvents(null);
    setError(null);
    getSessionEvents(sessionId)
      .then((evs) => {
        if (cancelled) return;
        setEvents(evs);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(errMessage(e));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, sessionId]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-2xl bg-surface text-on-surface border-outline-variant flex flex-col">

        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-on-surface-variant" />
            Session transcript
          </SheetTitle>
          <SheetDescription className="text-on-surface-variant">
            {workspaceName}
            {sessionId && (
              <>
                {" · "}
                <span className="font-mono text-[11px]">{sessionId}</span>
              </>
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 flex-1 overflow-y-auto pr-2">
          {sessionId === null && (
            <p className="text-caption text-on-surface-variant/70 italic py-8 text-center">
              No active session for this workspace yet. Start a task from
              the Kanban or send a prompt in Talk to spawn one.
            </p>
          )}
          {sessionId !== null && loading && (
            <p className="text-caption text-on-surface-variant py-4 text-center">
              Loading events…
            </p>
          )}
          {error && (
            <p className="text-caption text-error py-4" role="alert">
              {error}
            </p>
          )}
          {events !== null && events.length === 0 && (
            <p className="text-caption text-on-surface-variant/70 italic py-8 text-center">
              No events recorded for this session yet.
            </p>
          )}
          {events !== null && events.length > 0 && (
            <ol className="space-y-2">
              {events.map((ev, i) => {
                const tone = LEVEL_TONE[ev.level] ?? "text-on-surface-variant";
                const payloadKeys = Object.keys(ev.payload);
                return (
                  <li
                    key={i}
                    className="border-l-2 border-outline-variant/40 pl-3 py-1"
                  >
                    <div className="flex items-center gap-2 text-[10px] tabular-nums">
                      <span className="text-on-surface-variant">
                        {new Date(ev.ts).toLocaleTimeString()}
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-surface-container-low text-on-surface uppercase tracking-tight font-bold">
                        {ev.category}
                      </span>
                      <span className={`font-semibold ${tone}`}>
                        {ev.level}
                      </span>
                    </div>
                    <div className="text-caption text-on-surface mt-1 font-mono">
                      {ev.event}
                    </div>
                    {payloadKeys.length > 0 && (
                      <details className="mt-1">
                        <summary className="text-[10px] text-on-surface-variant cursor-pointer hover:text-on-surface">
                          payload ({payloadKeys.length} field
                          {payloadKeys.length === 1 ? "" : "s"})
                        </summary>
                        <pre className="text-[10px] font-mono text-on-surface-variant overflow-x-auto bg-surface-container-low p-2 rounded mt-1">
                          {JSON.stringify(ev.payload, null, 2)}
                        </pre>
                      </details>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
