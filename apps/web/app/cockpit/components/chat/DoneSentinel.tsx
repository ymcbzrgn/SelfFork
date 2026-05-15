/**
 * ``[SELFFORK:DONE]`` sentinel banner — Order 8.
 *
 * Mirror of the orchestrator's session-end protocol — when the
 * literal substring appears in a Jr message the cockpit surfaces a
 * "session marked done" banner so the operator doesn't have to
 * scroll to find it.
 */
"use client";

import type { ChatMessageResponse } from "@/lib/api";

const SENTINEL = "[SELFFORK:DONE]";

interface Props {
  content: string;
  /**
   * When provided, the banner only fires for assistant/tool roles —
   * the sentinel is a Jr → orchestrator signal, so an operator
   * literally typing ``[SELFFORK:DONE]`` in the chat input must NOT
   * trigger a "session done" banner (Order 8 audit Finding #3).
   * ``undefined`` keeps the legacy unconditional behaviour for
   * surfaces that already filter at the call site.
   */
  role?: ChatMessageResponse["role"];
}

export function DoneSentinel({ content, role }: Props) {
  if (!content.includes(SENTINEL)) return null;
  if (role === "user") return null;
  return (
    <div
      className="mt-2 rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-200"
      data-testid="chat-done-sentinel"
    >
      ✓ Session marked done by Jr (sentinel detected).
    </div>
  );
}
