"use client";

import { talkStreamUrl } from "@/lib/api";
import { useWebsocketSubscription } from "@/lib/ws/multiplex";
import type { WsEnvelope } from "@/lib/ws/types";

/**
 * Talk live-stream subscription (ADR-011 S-Stream).
 *
 * Renders nothing — it exists only to drive `useWebsocketSubscription`
 * for the active conversation. Routing the Talk feed through the shared
 * hook (instead of a raw `WebSocket`) gives sequence-aware reconnect with
 * `?last_seq=`, exponential backoff, and heartbeat-timeout detection — so
 * a transient drop mid-generation (the operator's CPU replies can take
 * minutes-to-hours) resumes the live token stream instead of stranding
 * the growing bubble. The server already buffers + replays by `seq`
 * (ws_protocol.py); this is the client half ADR-011 needs.
 *
 * Mounted conditionally (`conversationId` non-null) by the parent so the
 * hook — which cannot be called conditionally — only runs when there is a
 * conversation to stream. A conversation switch re-keys the `url`, which
 * the hook treats as a reconnect; unmount (new chat) closes the socket.
 */
export function TalkStreamSubscription({
  conversationId,
  onEnvelope,
}: {
  conversationId: string;
  onEnvelope: (env: WsEnvelope) => void;
}) {
  useWebsocketSubscription({
    url: talkStreamUrl(conversationId),
    onEnvelope,
  });
  return null;
}
