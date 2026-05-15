/**
 * Chat message list — Order 8.
 *
 * Renders bubbles top-to-bottom for the active branch. Auto-scrolls
 * when new messages arrive at the bottom (no virtualization here —
 * Order 7's react-virtuoso pattern is overkill for typical chat
 * lengths; M5+ wires it in if a session ever pushes past a few
 * hundred messages).
 */
"use client";

import { useEffect, useRef } from "react";

import type { ChatMessageResponse } from "@/lib/api";
import { useCockpitStore } from "@/lib/store";

import { MessageBubble } from "./MessageBubble";

interface Props {
  messages: ChatMessageResponse[];
}

export function MessageList({ messages }: Props) {
  const setEditing = useCockpitStore((s) => s.setChatEditingMessage);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (el === null) return;
    el.scrollTo({ top: el.scrollHeight });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border/60 p-6 text-sm text-muted-foreground">
        No messages yet — say hello in the input below.
      </div>
    );
  }
  return (
    <div
      ref={containerRef}
      className="max-h-[36rem] space-y-3 overflow-y-auto"
      data-testid="message-list"
    >
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} onEdit={setEditing} />
      ))}
    </div>
  );
}
