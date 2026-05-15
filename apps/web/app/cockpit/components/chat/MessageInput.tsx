/**
 * Chat input — Order 8.
 *
 * Two modes: append a new message (default), or commit an edit which
 * forks a new branch. Cmd/Ctrl+Enter submits.
 */
"use client";

import { useEffect, useState } from "react";

import { editChatMessage, postChatMessage } from "@/lib/api";
import { useCockpitStore } from "@/lib/store";

interface Props {
  sessionId: string;
  branchId: string | null;
  onSubmitted: () => void;
}

export function MessageInput({ sessionId, branchId, onSubmitted }: Props) {
  const editing = useCockpitStore((s) => s.chatEditingMessageId);
  const setEditing = useCockpitStore((s) => s.setChatEditingMessage);
  const [content, setContent] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editing === null) {
      setContent("");
    }
  }, [editing]);

  const submit = async () => {
    if (!content.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      if (editing !== null) {
        await editChatMessage(sessionId, editing, { content });
        setEditing(null);
      } else {
        await postChatMessage(sessionId, {
          content,
          role: "user",
          branch_id: branchId ?? undefined,
        });
      }
      setContent("");
      onSubmitted();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-2">
      {editing !== null ? (
        <div className="flex items-center justify-between text-xs text-amber-200">
          <span>Editing message — submit forks a new branch.</span>
          <button
            type="button"
            onClick={() => setEditing(null)}
            className="underline-offset-2 hover:underline"
          >
            cancel
          </button>
        </div>
      ) : null}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void submit();
          }
        }}
        placeholder={
          editing !== null
            ? "Rewrite this message…"
            : "Send Yamaç a message (Cmd/Ctrl+Enter to send)"
        }
        rows={3}
        className="w-full resize-y rounded-md border border-border bg-background p-2 text-sm"
        data-testid="chat-input"
      />
      {error ? (
        <p className="text-xs text-rose-300">Error: {error}</p>
      ) : null}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={pending || !content.trim()}
          className="rounded-md bg-primary px-3 py-1 text-sm font-medium text-primary-foreground disabled:opacity-40"
          data-testid="chat-submit"
        >
          {editing !== null ? "Save edit" : "Send"}
        </button>
      </div>
    </div>
  );
}
