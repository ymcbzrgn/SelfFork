/**
 * Vision Settings page — render + auto-detect + Apply flow tests.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import VisionSettingsPage from "@/app/cockpit/settings/vision/page";

const DEFAULT_CONFIG = {
  mlx_model_id: "mlx-community/gemma-4-E2B-it-4bit",
  mlx_server_url: "http://127.0.0.1:8080",
  ollama_model_tag: "gemma4:e2b-q4_K_M",
  ollama_host: "http://127.0.0.1:11434",
  auto_detect: false,
};

const DETECT_RESPONSE = {
  mlx_available: true,
  mlx_models: [
    "mlx-community/gemma-4-E2B-it-4bit",
    "mlx-community/gemma-4-E4B-it-4bit",
  ],
  mlx_error: null,
  ollama_available: false,
  ollama_models: [],
  ollama_error: "ConnectError: connection refused",
};

function mockJsonResponse<T>(data: T, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    json: async () => data,
  } as Response;
}

function installFetch(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";
      if (url === "/api/settings/vision" && method === "GET") {
        return mockJsonResponse(DEFAULT_CONFIG);
      }
      if (url === "/api/settings/vision" && method === "POST") {
        const body = JSON.parse((init?.body as string) ?? "{}");
        return mockJsonResponse({ ...DEFAULT_CONFIG, ...body });
      }
      if (url === "/api/settings/vision/detect") {
        return mockJsonResponse(DETECT_RESPONSE);
      }
      return mockJsonResponse({ detail: "not mocked" }, 404);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("VisionSettingsPage", () => {
  it("renders default config after GET /api/settings/vision", async () => {
    installFetch();
    render(<VisionSettingsPage />);
    await waitFor(() => {
      const input = screen.getByTestId("mlx-model-id") as HTMLInputElement;
      expect(input.value).toBe(DEFAULT_CONFIG.mlx_model_id);
    });
    const ollamaTag = screen.getByTestId("ollama-model-tag") as HTMLInputElement;
    expect(ollamaTag.value).toBe(DEFAULT_CONFIG.ollama_model_tag);
  });

  it("calls /detect when Auto-detect clicked", async () => {
    const fetchMock = installFetch();
    render(<VisionSettingsPage />);
    await waitFor(() => screen.getByTestId("mlx-model-id"));

    fireEvent.click(screen.getByTestId("detect-button"));

    await waitFor(() => {
      const detectCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          url === "/api/settings/vision/detect" && init?.method === "POST",
      );
      expect(detectCall).toBeDefined();
    });

    // Status text updates with adapter availability
    await waitFor(() => {
      expect(screen.getByText("available")).toBeTruthy();
      expect(screen.getByText("unreachable")).toBeTruthy();
    });
  });

  it("posts merged config when Apply clicked after edit", async () => {
    const fetchMock = installFetch();
    render(<VisionSettingsPage />);
    await waitFor(() => screen.getByTestId("mlx-model-id"));

    fireEvent.change(screen.getByTestId("mlx-model-id"), {
      target: { value: "custom-org/custom-gemma" },
    });
    fireEvent.click(screen.getByTestId("save-button"));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          url === "/api/settings/vision" && init?.method === "POST",
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse((postCall![1] as RequestInit).body as string);
      expect(body.mlx_model_id).toBe("custom-org/custom-gemma");
      // Untouched fields still submitted (full state PUT pattern)
      expect(body.ollama_model_tag).toBe(DEFAULT_CONFIG.ollama_model_tag);
    });

    // Success banner appears
    await waitFor(() => {
      expect(screen.getByText(/Saved/i)).toBeTruthy();
    });
  });
});
