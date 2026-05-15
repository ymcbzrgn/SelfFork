/**
 * Mission tab KanbanBoard render tests — Order 6.
 *
 * Drives the board with a synthetic ``KanbanResponse`` (matches the
 * real wire schema — no mocks, just a literal object the same shape
 * the dashboard emits) and asserts the layout responds to the
 * swimlane toggle + the handoff banner appears for in-progress cards
 * with a touched-by session.
 */
import { afterEach, describe, expect, it } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";

import { KanbanBoard } from "@/app/cockpit/components/mission/KanbanBoard";
import type { KanbanResponse } from "@/lib/api";
import { useCockpitStore } from "@/lib/store";

const initial = useCockpitStore.getState();

afterEach(() => {
  cleanup();
  useCockpitStore.setState(initial, true);
});

function makeBoard(): KanbanResponse {
  return {
    schema_version: 1,
    columns: ["backlog", "in_progress", "review", "done"],
    cards_by_column: {
      backlog: [
        {
          id: "c1",
          title: "Backlog A",
          body: "",
          column: "backlog",
          created_at: "2026-05-09T00:00:00Z",
          updated_at: "2026-05-09T00:00:00Z",
          completed_at: null,
          last_touched_by_session_id: null,
          order: null,
        },
      ],
      in_progress: [
        {
          id: "c2",
          title: "WIP B",
          body: "",
          column: "in_progress",
          created_at: "2026-05-09T00:00:00Z",
          updated_at: "2026-05-09T00:00:00Z",
          completed_at: null,
          last_touched_by_session_id: "01HJSESS",
          order: null,
        },
      ],
      review: [],
      done: [],
    },
  };
}

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("KanbanBoard", () => {
  it("renders four status columns", () => {
    renderWithQuery(<KanbanBoard slug="proj" board={makeBoard()} />);
    expect(screen.getByTestId("mission-column-backlog")).toBeInTheDocument();
    expect(screen.getByTestId("mission-column-in_progress")).toBeInTheDocument();
    expect(screen.getByTestId("mission-column-review")).toBeInTheDocument();
    expect(screen.getByTestId("mission-column-done")).toBeInTheDocument();
  });

  it("renders cards in the right column", () => {
    renderWithQuery(<KanbanBoard slug="proj" board={makeBoard()} />);
    const backlog = screen.getByTestId("mission-column-backlog");
    expect(backlog.textContent).toContain("Backlog A");
    const wip = screen.getByTestId("mission-column-in_progress");
    expect(wip.textContent).toContain("WIP B");
  });

  it("renders the handoff lane when a touched-by session is in progress", () => {
    renderWithQuery(<KanbanBoard slug="proj" board={makeBoard()} />);
    const lane = screen.getByTestId("mission-handoff-lane");
    expect(lane).toBeInTheDocument();
    expect(lane.textContent).toContain("WIP B");
    expect(lane.textContent).toContain("01HJSESS");
  });

  it("clicking a card sets the active card in the store", () => {
    renderWithQuery(<KanbanBoard slug="proj" board={makeBoard()} />);
    const card = screen.getByTestId("mission-card-c1");
    fireEvent.click(card);
    expect(useCockpitStore.getState().missionActiveCardId).toBe("c1");
  });

  it("swimlane toggle switches to the session view", () => {
    renderWithQuery(<KanbanBoard slug="proj" board={makeBoard()} />);
    expect(screen.getByTestId("mission-kanban-status")).toBeInTheDocument();
    // Click the "By session" radio.
    const session = screen.getByText("By session");
    fireEvent.click(session);
    expect(screen.getByTestId("mission-kanban-session")).toBeInTheDocument();
    expect(useCockpitStore.getState().missionSwimlaneMode).toBe("session");
  });
});
