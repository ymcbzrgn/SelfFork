/**
 * Providers slice (M5 — ADR-005 §M5-E).
 *
 * Tracks subscription provider auth state for the cockpit's "Providers" tab.
 * Read-only mirror of the orchestrator's storage_state catalogue; mutations
 * happen via REST endpoints in :mod:`provider_router` (sign_in / refresh /
 * disconnect) and the slice updates from the response.
 */
import type { StateCreator } from "zustand";

import type { CockpitStore } from "./index";

export type ProviderName =
  | "claude_pro"
  | "codex"
  | "gemini"
  | "opencode"
  | "mmx";

export type ProviderStatus =
  | "connected"
  | "disconnected"
  | "expired"
  | "expiring_soon";

export interface ProviderState {
  name: ProviderName;
  status: ProviderStatus;
  expires_at: string | null;
  last_sign_in: string | null;
  last_error: string | null;
}

export interface ProvidersSlice {
  providers: Record<ProviderName, ProviderState>;
  signInSessionId: string | null;
  setProviders: (providers: ProviderState[]) => void;
  setProviderState: (name: ProviderName, state: Partial<ProviderState>) => void;
  setSignInSession: (id: string | null) => void;
}

const PROVIDERS: ProviderName[] = [
  "claude_pro",
  "codex",
  "gemini",
  "opencode",
  "mmx",
];

const initialProviderState = (name: ProviderName): ProviderState => ({
  name,
  status: "disconnected",
  expires_at: null,
  last_sign_in: null,
  last_error: null,
});

export const createProvidersSlice: StateCreator<
  CockpitStore,
  [["zustand/devtools", never]],
  [],
  ProvidersSlice
> = (set) => ({
  providers: PROVIDERS.reduce<Record<ProviderName, ProviderState>>(
    (acc, name) => {
      acc[name] = initialProviderState(name);
      return acc;
    },
    {} as Record<ProviderName, ProviderState>,
  ),
  signInSessionId: null,
  setProviders: (providers) =>
    set(
      (state) => {
        const next = { ...state.providers };
        for (const provider of providers) {
          next[provider.name] = provider;
        }
        return { providers: next };
      },
      false,
      "providers/set",
    ),
  setProviderState: (name, partial) =>
    set(
      (state) => ({
        providers: {
          ...state.providers,
          [name]: { ...state.providers[name], ...partial },
        },
      }),
      false,
      "providers/setOne",
    ),
  setSignInSession: (id) =>
    set({ signInSessionId: id }, false, "providers/setSignInSession"),
});
