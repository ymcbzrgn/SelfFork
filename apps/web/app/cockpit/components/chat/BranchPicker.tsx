/**
 * Branch picker — Order 8.
 *
 * Tiny Previous/Next/N-of-M control modelled on assistant-ui's
 * ``BranchPickerPrimitive``. Visible only when the current message
 * has at least one alternative branch — for linear sessions the
 * picker is invisible.
 */
"use client";

import type { BranchResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  branches: BranchResponse[];
  activeBranchId: string | null;
  onSelect: (id: string) => void;
  /**
   * When set, only branches that fork from this message are shown
   * (assistant-ui semantics: the picker scopes to siblings of the
   * current message, not every branch in the session). When null/
   * undefined the picker walks the entire session-wide branch list
   * — used as a session-level fallback navigator.
   */
  forkMessageId?: string | null;
}

export function BranchPicker({
  branches,
  activeBranchId,
  onSelect,
  forkMessageId,
}: Props) {
  // Order 8 audit fix: previously the picker walked all session
  // branches regardless of the message context. Filter to siblings
  // forked from the same message + the parent branch (the one whose
  // child this fork is).
  const visible = forkMessageId
    ? branches.filter(
        (b) =>
          b.fork_message_id === forkMessageId ||
          // include the parent branch so "go back to before the edit"
          // is still one click away
          (activeBranchId !== null &&
            branches.find((c) => c.id === activeBranchId)
              ?.parent_branch_id === b.id),
      )
    : branches;
  if (visible.length < 2) return null;
  const rawIdx = visible.findIndex((b) => b.id === activeBranchId);
  // Order 8 audit fix: ``Math.max(0, -1)`` previously hid stale-prop
  // mismatches by silently activating the first branch; now we just
  // refuse to render rather than mislead the operator.
  if (rawIdx === -1) return null;
  const prev = visible[rawIdx - 1];
  const next = visible[rawIdx + 1];
  return (
    <div
      className="inline-flex items-center gap-2 text-xs"
      data-testid="chat-branch-picker"
    >
      <BranchButton
        label="◀"
        onClick={() => prev && onSelect(prev.id)}
        disabled={!prev}
      />
      <span className="font-mono">
        {rawIdx + 1} / {visible.length}
      </span>
      <BranchButton
        label="▶"
        onClick={() => next && onSelect(next.id)}
        disabled={!next}
      />
      <span className="font-mono text-muted-foreground">
        {visible[rawIdx]?.label ?? ""}
      </span>
    </div>
  );
}

function BranchButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded border border-border/60 px-2 py-0.5 transition-colors",
        disabled
          ? "cursor-not-allowed opacity-40"
          : "hover:border-foreground/40",
      )}
    >
      {label}
    </button>
  );
}
