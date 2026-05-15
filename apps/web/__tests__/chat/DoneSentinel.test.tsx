import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { DoneSentinel } from "@/app/cockpit/components/chat/DoneSentinel";

afterEach(() => cleanup());

describe("DoneSentinel", () => {
  it("renders when [SELFFORK:DONE] is in the content", () => {
    render(<DoneSentinel content="all good now [SELFFORK:DONE]" />);
    expect(screen.getByTestId("chat-done-sentinel")).toBeInTheDocument();
  });

  it("renders nothing for messages without the sentinel", () => {
    const { container } = render(<DoneSentinel content="hello world" />);
    expect(container.firstChild).toBeNull();
  });

  it("matches the exact substring (no fuzzy matching)", () => {
    const { container } = render(<DoneSentinel content="[SELFFORK]done" />);
    expect(container.firstChild).toBeNull();
  });

  it("does NOT fire for user messages even with the literal sentinel", () => {
    // Order 8 audit Finding #3 fix: operator typing
    // ``[SELFFORK:DONE]`` in the chat input previously raised the
    // banner. Sentinel is a Jr→orchestrator signal, not a user one.
    const { container } = render(
      <DoneSentinel content="[SELFFORK:DONE] please" role="user" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("fires for assistant messages with the sentinel", () => {
    render(
      <DoneSentinel
        content="all good [SELFFORK:DONE]"
        role="assistant"
      />,
    );
    expect(screen.getByTestId("chat-done-sentinel")).toBeInTheDocument();
  });
});
