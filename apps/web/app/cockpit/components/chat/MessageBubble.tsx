/**
 * Single chat message — Order 8.
 *
 * Streamdown handles the markdown render (incl. mid-stream
 * unterminated blocks, code highlighting, copy buttons). When the
 * message is currently streaming we read tokens out of the cockpit
 * store; finalised messages render their persisted ``content``.
 */
"use client";

import { Streamdown } from "streamdown";

import { useCockpitStore } from "@/lib/store";
import type { ChatMessageResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

import { DoneSentinel } from "./DoneSentinel";

export function MessageBubble({
  message,
  onEdit,
}: {
  message: ChatMessageResponse;
  onEdit: (id: string) => void;
}) {
  const streamingTokens = useCockpitStore((s) => s.chatStreamingTokens);
  const buffered = streamingTokens[message.id];
  const content = buffered ?? message.content;

  return (
    <div
      className={cn(
        "rounded-md border border-border/40 bg-card/40 p-3",
        message.role === "user" ? "border-foreground/30" : "",
      )}
      data-testid={`message-bubble-${message.id}`}
      data-role={message.role}
    >
      <div className="mb-1 flex items-center justify-between text-[11px]">
        <span className="font-mono uppercase text-muted-foreground">
          {message.role}
        </span>
        {message.role === "user" ? (
          <button
            type="button"
            onClick={() => onEdit(message.id)}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
            data-testid={`message-edit-${message.id}`}
          >
            edit
          </button>
        ) : null}
      </div>
      <div className="prose prose-sm prose-invert max-w-none">
        <Streamdown>{content}</Streamdown>
      </div>
      <DoneSentinel content={content} role={message.role} />
    </div>
  );
}
