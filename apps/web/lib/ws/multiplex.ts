/**
 * ``useWebsocketSubscription`` — M-1 protocol client. Order 5.
 *
 * One WebSocket per call site, with:
 *
 * 1. Sequence-aware reconnect — the hook tracks the last ``seq`` it
 *    delivered to the caller and reconnects with ``?last_seq=N`` so
 *    the server can replay missed envelopes.
 * 2. Exponential backoff capped at 30 s.
 * 3. Heartbeat detection — if no envelope (heartbeat included)
 *    arrives within ``heartbeatTimeoutMs`` (35 s default), force a
 *    reconnect rather than waiting for the OS socket timeout.
 * 4. Gap detection — when an envelope's ``seq`` jumps past the next
 *    expected value, the optional ``onGap`` callback fires with the
 *    boundary so the caller can backfill via REST.
 *
 * The hook returns a stable ``status`` value plus a ``reconnect()``
 * imperative escape hatch tests use to flush the loop.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { WsEnvelope } from "@/lib/ws/types";

export type WsConnectionStatus =
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed";

export interface UseWebsocketSubscriptionArgs {
  url: string;
  onEnvelope: (env: WsEnvelope) => void;
  onGap?: (lastSeq: number, newSeq: number) => void;
  onStatusChange?: (status: WsConnectionStatus) => void;
  heartbeatTimeoutMs?: number;
  /**
   * Override for tests — defaults to ``window.WebSocket``. The
   * constructor signature must match the WebSocket class so the hook
   * can call ``new WebSocketCtor(url)``.
   */
  webSocketImpl?: typeof WebSocket;
}

const HEARTBEAT_TIMEOUT_DEFAULT_MS = 35_000;
const BACKOFF_MIN_MS = 500;
const BACKOFF_MAX_MS = 30_000;

export function useWebsocketSubscription(
  args: UseWebsocketSubscriptionArgs,
): { status: WsConnectionStatus; reconnect: () => void } {
  const {
    url,
    onEnvelope,
    onGap,
    onStatusChange,
    heartbeatTimeoutMs = HEARTBEAT_TIMEOUT_DEFAULT_MS,
    webSocketImpl,
  } = args;

  const [status, setStatus] = useState<WsConnectionStatus>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const lastSeqRef = useRef<number>(0);
  const attemptRef = useRef<number>(0);
  const heartbeatTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByCallerRef = useRef<boolean>(false);

  const updateStatus = useCallback(
    (next: WsConnectionStatus) => {
      setStatus(next);
      onStatusChange?.(next);
    },
    [onStatusChange],
  );

  const clearHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current !== null) {
      clearTimeout(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  const armHeartbeat = useCallback(() => {
    clearHeartbeat();
    heartbeatTimerRef.current = setTimeout(() => {
      // No envelope (incl. heartbeat) within the timeout window —
      // half-open TCP. Force reconnect.
      const ws = wsRef.current;
      if (ws !== null) {
        try {
          ws.close();
        } catch {
          // ignore — close() throws if already closing.
        }
      }
    }, heartbeatTimeoutMs);
  }, [heartbeatTimeoutMs, clearHeartbeat]);

  const open = useCallback(() => {
    closedByCallerRef.current = false;
    const Ctor = webSocketImpl ?? WebSocket;
    const u = appendLastSeq(url, lastSeqRef.current);
    let ws: WebSocket;
    try {
      ws = new Ctor(u);
    } catch {
      // Constructor failures (invalid URL, blocked, etc.) — schedule a
      // reconnect rather than throw out of the hook.
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;
    updateStatus(attemptRef.current === 0 ? "connecting" : "reconnecting");
    armHeartbeat();

    ws.onopen = () => {
      attemptRef.current = 0;
      updateStatus("open");
      armHeartbeat();
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      armHeartbeat();
      let env: WsEnvelope;
      try {
        env = JSON.parse(event.data) as WsEnvelope;
      } catch {
        return; // malformed frame — drop, no state change
      }
      // Heartbeats keep the connection alive but the caller doesn't
      // care about them (most surfaces filter them out anyway).
      if (env.event_type === "heartbeat") {
        lastSeqRef.current = Math.max(lastSeqRef.current, env.seq);
        return;
      }
      const expected = lastSeqRef.current + 1;
      if (env.seq > expected && lastSeqRef.current > 0 && onGap) {
        onGap(lastSeqRef.current, env.seq);
      }
      lastSeqRef.current = env.seq;
      onEnvelope(env);
    };

    ws.onerror = () => {
      // Browsers fire ``close`` after ``error``; let onclose handle
      // the reconnect bookkeeping.
    };

    ws.onclose = () => {
      clearHeartbeat();
      if (closedByCallerRef.current) {
        updateStatus("closed");
        return;
      }
      scheduleReconnect();
    };
  }, [url, webSocketImpl, onEnvelope, onGap, updateStatus, armHeartbeat, clearHeartbeat]);

  const scheduleReconnect = useCallback(() => {
    updateStatus("reconnecting");
    const attempt = attemptRef.current + 1;
    attemptRef.current = attempt;
    const backoff = Math.min(
      BACKOFF_MAX_MS,
      BACKOFF_MIN_MS * 2 ** Math.min(attempt - 1, 6),
    );
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      open();
    }, backoff);
  }, [open, updateStatus]);

  const reconnect = useCallback(() => {
    const ws = wsRef.current;
    if (ws !== null) {
      try {
        ws.close();
      } catch {
        // ignore
      }
    }
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    attemptRef.current = 0;
    open();
  }, [open]);

  useEffect(() => {
    open();
    return () => {
      closedByCallerRef.current = true;
      clearHeartbeat();
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      if (ws !== null) {
        try {
          ws.close();
        } catch {
          // ignore
        }
        wsRef.current = null;
      }
    };
    // ``url`` change should rebuild the connection; the rest of the
    // dependency surface is stable refs / setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  return { status, reconnect };
}

function appendLastSeq(url: string, lastSeq: number): string {
  if (lastSeq <= 0) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}last_seq=${lastSeq}`;
}
