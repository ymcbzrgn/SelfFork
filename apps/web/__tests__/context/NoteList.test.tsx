import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { NoteList } from "@/app/cockpit/components/context/NoteList";
import type { NoteResponse } from "@/lib/api";

afterEach(() => cleanup());

function makeNote(overrides: Partial<NoteResponse> = {}): NoteResponse {
  return {
    id: "n1",
    tier: "episodic",
    kind: "observation",
    content: "Hello note",
    intent: "demo",
    importance: 0.5,
    pinned: false,
    project_slug: "calc",
    session_id: "sess",
    valid_from: "2026-05-09T18:00:00Z",
    valid_until: null,
    tag_keys: ["tag-a"],
    path_scope: [],
    always_apply: false,
    ...overrides,
  };
}

describe("NoteList", () => {
  it("renders a placeholder when empty", () => {
    render(<NoteList notes={[]} />);
    expect(
      screen.getByText(/No notes in this tier/),
    ).toBeInTheDocument();
  });

  it("renders one row per note", () => {
    render(
      <NoteList
        notes={[makeNote(), makeNote({ id: "n2", content: "second" })]}
      />,
    );
    expect(screen.getByTestId("note-n1")).toBeInTheDocument();
    expect(screen.getByTestId("note-n2")).toBeInTheDocument();
    expect(screen.getByText(/Hello note/)).toBeInTheDocument();
    expect(screen.getByText("second")).toBeInTheDocument();
  });

  it("surfaces pinned + importance + tag chips", () => {
    render(
      <NoteList
        notes={[makeNote({ pinned: true, importance: 1.25 })]}
      />,
    );
    expect(screen.getByText(/pinned/)).toBeInTheDocument();
    expect(screen.getByText(/importance 1.25/)).toBeInTheDocument();
    expect(screen.getByText(/tag-a/)).toBeInTheDocument();
  });
});
