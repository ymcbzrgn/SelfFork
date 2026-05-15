/**
 * Live audit-stream view — Order 7.
 *
 * Backed by react-virtuoso so the list scales past 10K events. The
 * ``followOutput="smooth"`` prop sticks the view to the bottom while
 * the stream is live; pausing happens automatically when the user
 * scrolls up (``atBottomStateChange``).
 *
 * The component subscribes to the M-1 WS endpoint via
 * ``useWebsocketSubscription``; new envelopes are appended to the
 * TanStack Query cache so other surfaces (TraceTree, Waterfall) can
 * read the same array.
 */
"use client";

import { useState } from "react";
import { Virtuoso } from "react-virtuoso";

import { sessionStreamUrl, type AuditEvent } from "@/lib/api";
import { cockpitKeys, queryClient } from "@/lib/query";
import { useCockpitStore } from "@/lib/store";
import { useWebsocketSubscription } from "@/lib/ws/multiplex";

import { EventRow } from "./EventRow";

interface Props {
  sessionId: string;
  events: AuditEvent[];
}

export function AuditStream({ sessionId, events }: Props) {
  const setLastSeq = useCockpitStore((s) => s.setRunLastSeq);
  const [atBottom, setAtBottom] = useState<boolean>(true);

  useWebsocketSubscription({
    url: sessionStreamUrl(sessionId),
    onEnvelope: (env) => {
      if (env.event_type !== "audit") return;
      setLastSeq(env.seq);
      const payload = env.payload as unknown as AuditEvent;
      queryClient.setQueryData(
        cockpitKeys.audit(sessionId),
        (prev: AuditEvent[] | undefined) => [...(prev ?? []), payload],
      );
    },
    onGap: (last, next) => {
      // M-1 §gap: client should backfill the missing range via REST.
      // Order 7 keeps it simple — re-prime the cache so existing
      // surfaces see the full event list. (REST fetcher TBD; M5+
      // wires a targeted ``GET /events?from=…`` endpoint.)
      void queryClient.invalidateQueries({
        queryKey: cockpitKeys.audit(sessionId),
      });
      void last;
      void next;
    },
  });

  return (
    <div
      className="h-[24rem] rounded-md border border-border/60 bg-background"
      data-testid="audit-stream"
    >
      <Virtuoso
        data={events}
        followOutput={atBottom ? "smooth" : false}
        atBottomStateChange={(b) => setAtBottom(b)}
        itemContent={(_, ev) => <EventRow event={ev} />}
        increaseViewportBy={300}
      />
    </div>
  );
}
