/**
 * useWebsocketSubscription unit tests — Order 5.
 *
 * Uses a hand-rolled fake ``WebSocket`` so we can drive the hook
 * deterministically without a live server. Vitest's fake timers
 * handle the heartbeat + backoff schedules.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  useWebsocketSubscription,
  type WsConnectionStatus,
} from "@/lib/ws/multiplex";
import type { WsEnvelope } from "@/lib/ws/types";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent<string>) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    this.onclose?.(new Event("close") as CloseEvent);
  }
  // Helpers for tests.
  fireOpen() {
    this.onopen?.(new Event("open"));
  }
  fireMessage(env: WsEnvelope) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(env) }),
    );
  }
  fireError() {
    this.onerror?.(new Event("error"));
  }
}

function makeEnv(seq: number, eventType: WsEnvelope["event_type"] = "audit"): WsEnvelope {
  return {
    seq,
    event_type: eventType,
    payload: { seq },
    ts: new Date().toISOString(),
  };
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useWebsocketSubscription", () => {
  it("calls onEnvelope for each non-heartbeat frame", () => {
    const received: WsEnvelope[] = [];
    renderHook(() =>
      useWebsocketSubscription({
        url: "ws://x/stream",
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
        onEnvelope: (e) => received.push(e),
      }),
    );
    const ws = FakeWebSocket.instances.at(-1)!;
    act(() => ws.fireOpen());
    act(() => ws.fireMessage(makeEnv(1)));
    act(() => ws.fireMessage(makeEnv(2)));
    expect(received.map((e) => e.seq)).toEqual([1, 2]);
  });

  it("filters out heartbeat frames from onEnvelope", () => {
    const received: WsEnvelope[] = [];
    renderHook(() =>
      useWebsocketSubscription({
        url: "ws://x/stream",
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
        onEnvelope: (e) => received.push(e),
      }),
    );
    const ws = FakeWebSocket.instances.at(-1)!;
    act(() => ws.fireOpen());
    act(() => ws.fireMessage(makeEnv(1, "heartbeat")));
    act(() => ws.fireMessage(makeEnv(2)));
    expect(received.map((e) => e.seq)).toEqual([2]);
  });

  it("invokes onGap when seq jumps past the next expected value", () => {
    const onGap = vi.fn();
    renderHook(() =>
      useWebsocketSubscription({
        url: "ws://x/stream",
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
        onEnvelope: () => undefined,
        onGap,
      }),
    );
    const ws = FakeWebSocket.instances.at(-1)!;
    act(() => ws.fireOpen());
    act(() => ws.fireMessage(makeEnv(1)));
    // Skip seq 2 — server should have emitted a gap envelope.
    act(() => ws.fireMessage(makeEnv(5)));
    expect(onGap).toHaveBeenCalledWith(1, 5);
  });

  it("reconnects with ?last_seq=N after the socket closes", () => {
    const received: WsEnvelope[] = [];
    renderHook(() =>
      useWebsocketSubscription({
        url: "ws://x/stream",
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
        onEnvelope: (e) => received.push(e),
      }),
    );
    const first = FakeWebSocket.instances.at(-1)!;
    act(() => first.fireOpen());
    act(() => first.fireMessage(makeEnv(7)));
    act(() => first.close());

    // Backoff window — advance.
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    const second = FakeWebSocket.instances.at(-1)!;
    expect(second).not.toBe(first);
    expect(second.url).toContain("last_seq=7");
  });

  it("status transitions: connecting → open → reconnecting → open", async () => {
    const transitions: WsConnectionStatus[] = [];
    renderHook(() =>
      useWebsocketSubscription({
        url: "ws://x/stream",
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
        onEnvelope: () => undefined,
        onStatusChange: (s) => transitions.push(s),
      }),
    );
    const first = FakeWebSocket.instances.at(-1)!;
    act(() => first.fireOpen());
    act(() => first.close());
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    const second = FakeWebSocket.instances.at(-1)!;
    act(() => second.fireOpen());
    expect(transitions).toContain("connecting");
    expect(transitions).toContain("open");
    expect(transitions).toContain("reconnecting");
    await waitFor(() =>
      expect(transitions[transitions.length - 1]).toBe("open"),
    );
  });

  it("cleans up on unmount", () => {
    const { unmount } = renderHook(() =>
      useWebsocketSubscription({
        url: "ws://x/stream",
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
        onEnvelope: () => undefined,
      }),
    );
    const ws = FakeWebSocket.instances.at(-1)!;
    expect(ws.closed).toBe(false);
    unmount();
    expect(ws.closed).toBe(true);
  });

  it("does not reconnect after caller-initiated unmount", () => {
    const { unmount } = renderHook(() =>
      useWebsocketSubscription({
        url: "ws://x/stream",
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
        onEnvelope: () => undefined,
      }),
    );
    unmount();
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    // Only the original instance — no reconnect was scheduled.
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
