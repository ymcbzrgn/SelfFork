/**
 * TierSection render tests — Order 9.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { TierSection } from "@/app/cockpit/components/context/TierSection";
import { useCockpitStore } from "@/lib/store";

const initial = useCockpitStore.getState();

afterEach(() => {
  cleanup();
  useCockpitStore.setState(initial, true);
});

describe("TierSection", () => {
  it("renders the tier title + count + last-updated", () => {
    render(
      <TierSection
        tier="working"
        title="Working"
        count={3}
        lastUpdated="2026-05-09T18:00:00Z"
      >
        body
      </TierSection>,
    );
    expect(screen.getByText("Working")).toBeInTheDocument();
    expect(screen.getByTestId("tier-count-working")).toHaveTextContent(
      "3 notes",
    );
  });

  it("renders an em-dash placeholder when no last-updated", () => {
    render(
      <TierSection
        tier="reflection"
        title="Reflection"
        count={0}
        lastUpdated={null}
      >
        body
      </TierSection>,
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("expands by default for default-expanded tiers", () => {
    render(
      <TierSection
        tier="working"
        title="Working"
        count={1}
        lastUpdated={null}
      >
        body
      </TierSection>,
    );
    const det = screen.getByTestId("tier-section-working") as HTMLDetailsElement;
    expect(det.open).toBe(true);
  });

  it("toggling the store flips the collapsed state in the next render", () => {
    const { rerender } = render(
      <TierSection
        tier="reflection"
        title="Reflection"
        count={1}
        lastUpdated={null}
      >
        body
      </TierSection>,
    );
    const det = screen.getByTestId("tier-section-reflection") as HTMLDetailsElement;
    expect(det.open).toBe(false); // not in DEFAULT_EXPANDED
    useCockpitStore.getState().toggleContextTier("reflection");
    rerender(
      <TierSection
        tier="reflection"
        title="Reflection"
        count={1}
        lastUpdated={null}
      >
        body
      </TierSection>,
    );
    expect(
      (
        screen.getByTestId("tier-section-reflection") as HTMLDetailsElement
      ).open,
    ).toBe(true);
  });
});
