/**
 * BranchPicker render tests — Order 8.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { BranchPicker } from "@/app/cockpit/components/chat/BranchPicker";
import type { BranchResponse } from "@/lib/api";

afterEach(() => cleanup());

function makeBranches(n: number): BranchResponse[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `b${i}`,
    session_id: "sess",
    parent_branch_id: i === 0 ? null : `b${i - 1}`,
    fork_message_id: i === 0 ? null : `m${i - 1}`,
    label: i === 0 ? "main" : `alt-${i}`,
    is_active: i === 0,
    created_at: "2026-05-09T18:00:00Z",
  }));
}

describe("BranchPicker", () => {
  it("renders nothing for a single branch", () => {
    const { container } = render(
      <BranchPicker
        branches={makeBranches(1)}
        activeBranchId="b0"
        onSelect={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders the count for two branches", () => {
    render(
      <BranchPicker
        branches={makeBranches(2)}
        activeBranchId="b0"
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("chat-branch-picker")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("invokes onSelect with the next branch id", () => {
    const onSelect = vi.fn();
    render(
      <BranchPicker
        branches={makeBranches(3)}
        activeBranchId="b0"
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByText("▶"));
    expect(onSelect).toHaveBeenCalledWith("b1");
  });

  it("disables prev at the head", () => {
    render(
      <BranchPicker
        branches={makeBranches(3)}
        activeBranchId="b0"
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText("◀")).toBeDisabled();
  });

  it("disables next at the tail", () => {
    render(
      <BranchPicker
        branches={makeBranches(3)}
        activeBranchId="b2"
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText("▶")).toBeDisabled();
  });

  it("scopes to siblings of forkMessageId when provided", () => {
    // Order 8 audit Finding #2 fix: assistant-ui semantics — picker
    // shows only branches that fork from the same message (+ the
    // parent branch as a "go back" option).
    const branches: BranchResponse[] = [
      // Main branch
      {
        id: "main",
        session_id: "s",
        parent_branch_id: null,
        fork_message_id: null,
        label: "main",
        is_active: false,
        created_at: "t0",
      },
      // Two siblings forked from message X
      {
        id: "alt-1",
        session_id: "s",
        parent_branch_id: "main",
        fork_message_id: "msg-x",
        label: "alt-1",
        is_active: true,
        created_at: "t1",
      },
      {
        id: "alt-2",
        session_id: "s",
        parent_branch_id: "main",
        fork_message_id: "msg-x",
        label: "alt-2",
        is_active: false,
        created_at: "t2",
      },
      // Unrelated fork from a different message
      {
        id: "alt-other",
        session_id: "s",
        parent_branch_id: "main",
        fork_message_id: "msg-y",
        label: "alt-other",
        is_active: false,
        created_at: "t3",
      },
    ];
    render(
      <BranchPicker
        branches={branches}
        activeBranchId="alt-1"
        onSelect={() => {}}
        forkMessageId="msg-x"
      />,
    );
    // 3 visible: main (parent), alt-1 (active), alt-2 (sibling).
    // alt-other excluded because it forks from a different message.
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("returns null when activeBranchId is missing from branches list (stale prop)", () => {
    const { container } = render(
      <BranchPicker
        branches={makeBranches(3)}
        activeBranchId="not-in-list"
        onSelect={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});
