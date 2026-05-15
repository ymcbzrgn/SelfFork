/**
 * Cockpit Providers view (M5 — ADR-005 §M5-E).
 *
 * Read-only auth status + browser-driven sign-in trigger for the five
 * subscription providers. Claude Pro automation is opt-in only with an
 * explicit ToS warning banner.
 */
"use client";

import { useEffect } from "react";

import {
  useCockpitStore,
  type ProviderName,
  type ProviderState,
} from "@/lib/store";

const PROVIDERS: { name: ProviderName; label: string; tos_warning?: string }[] =
  [
    {
      name: "claude_pro",
      label: "Claude Pro / Max",
      tos_warning:
        "Browser automation of Claude Pro login may violate Anthropic ToS — opt in only.",
    },
    { name: "codex", label: "ChatGPT Plus (codex)" },
    { name: "gemini", label: "Google Code Assist (gemini)" },
    { name: "opencode", label: "Z.AI Coding Plan (opencode)" },
    { name: "mmx", label: "Minimax sub (mmx)" },
  ];

function StatusBadge({ status }: { status: ProviderState["status"] }) {
  const colour = {
    connected: "bg-green-100 text-green-800",
    disconnected: "bg-zinc-100 text-zinc-700",
    expired: "bg-red-100 text-red-800",
    expiring_soon: "bg-amber-100 text-amber-900",
  }[status];
  return (
    <span className={`inline-block text-xs rounded px-2 py-0.5 ${colour}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function ProviderCard({
  name,
  label,
  tos_warning,
  state,
  onSignIn,
  onRefresh,
  onDisconnect,
}: {
  name: ProviderName;
  label: string;
  tos_warning?: string;
  state: ProviderState;
  onSignIn: () => void;
  onRefresh: () => void;
  onDisconnect: () => void;
}) {
  return (
    <div
      className="border rounded p-4 space-y-3"
      data-testid={`provider-card-${name}`}
    >
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">{label}</h2>
        <StatusBadge status={state.status} />
      </div>
      {tos_warning ? (
        <div className="text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded">
          ⚠ {tos_warning}
        </div>
      ) : null}
      {state.expires_at ? (
        <div className="text-xs text-zinc-500">
          Expires: {state.expires_at}
        </div>
      ) : null}
      {state.last_error ? (
        <div className="text-xs text-red-600">{state.last_error}</div>
      ) : null}
      <div className="flex gap-2 text-sm">
        <button
          type="button"
          className="rounded px-3 py-1 bg-blue-600 text-white hover:bg-blue-700"
          onClick={onSignIn}
        >
          Sign in with browser
        </button>
        <button
          type="button"
          className="rounded px-3 py-1 bg-zinc-100 hover:bg-zinc-200 disabled:opacity-50"
          disabled={state.status === "disconnected"}
          onClick={onRefresh}
        >
          Refresh token
        </button>
        <button
          type="button"
          className="rounded px-3 py-1 bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-50"
          disabled={state.status === "disconnected"}
          onClick={onDisconnect}
        >
          Disconnect
        </button>
      </div>
    </div>
  );
}

export default function ProvidersPage() {
  const providers = useCockpitStore((s) => s.providers);
  const setProviders = useCockpitStore((s) => s.setProviders);
  const setSignInSession = useCockpitStore((s) => s.setSignInSession);
  const setProviderState = useCockpitStore((s) => s.setProviderState);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/providers")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data: ProviderState[]) => {
        if (!cancelled) setProviders(data);
      })
      .catch(() => {
        // backend offline → keep slice defaults
      });
    return () => {
      cancelled = true;
    };
  }, [setProviders]);

  const signIn = async (name: ProviderName) => {
    const r = await fetch(`/api/providers/${name}/sign_in_start`, {
      method: "POST",
    });
    if (!r.ok) {
      setProviderState(name, { last_error: `sign_in_start ${r.status}` });
      return;
    }
    const body = await r.json();
    setSignInSession(body.session_id);
  };

  const refresh = async (name: ProviderName) => {
    await fetch(`/api/providers/${name}/refresh`, { method: "POST" });
  };

  const disconnect = async (name: ProviderName) => {
    const r = await fetch(`/api/providers/${name}/disconnect`, {
      method: "POST",
    });
    if (r.ok) {
      setProviderState(name, { status: "disconnected", expires_at: null });
    }
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Providers</h1>
      <p className="text-sm text-zinc-500">
        Subscription OAuth catalogue. API keys are never accepted —
        sign-in flows go through the body web driver and persist as Playwright
        ``storage_state`` per project.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {PROVIDERS.map(({ name, label, tos_warning }) => (
          <ProviderCard
            key={name}
            name={name}
            label={label}
            tos_warning={tos_warning}
            state={providers[name]}
            onSignIn={() => signIn(name)}
            onRefresh={() => refresh(name)}
            onDisconnect={() => disconnect(name)}
          />
        ))}
      </div>
    </div>
  );
}
