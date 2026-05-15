/**
 * Connections — Stitch-verbatim port. AI assistants list, real
 * /api/providers. "Connect" → POST sign_in_start (currently a
 * backend stub that returns 200 without opening a browser — UI
 * notes that honestly until the body web driver lands the OAuth
 * orchestration).
 *
 * Stitch design reference: screen fb678a31f97644fd95996e3aa4710f42.
 */
"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { API_BASE } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ProviderRow {
  name: "claude_pro" | "codex" | "gemini" | "opencode" | "mmx";
  label: string;
  description: string;
  letter: string;
  swatch: string;
}

interface ProviderState {
  name: ProviderRow["name"];
  status: "connected" | "disconnected" | "expired" | "expiring_soon";
  expires_at: string | null;
  last_sign_in: string | null;
  last_error: string | null;
  storage_state_path: string | null;
}

const PROVIDERS: ProviderRow[] = [
  {
    name: "claude_pro",
    label: "Claude",
    description: "Anthropic's flagship coding assistant",
    letter: "C",
    swatch: "bg-gradient-to-br from-orange-100 to-amber-50",
  },
  {
    name: "codex",
    label: "ChatGPT",
    description: "OpenAI's versatile language model",
    letter: "G",
    swatch: "bg-gradient-to-br from-emerald-100 to-teal-50",
  },
  {
    name: "gemini",
    label: "Gemini",
    description: "Google's multi-modal AI intelligence",
    letter: "G",
    swatch: "bg-gradient-to-br from-blue-100 to-sky-50",
  },
  {
    name: "opencode",
    label: "OpenCode",
    description: "Community-driven open source models",
    letter: "O",
    swatch: "bg-gradient-to-br from-slate-100 to-zinc-50",
  },
  {
    name: "mmx",
    label: "MiniMax",
    description: "High-performance reasoning engine",
    letter: "M",
    swatch: "bg-gradient-to-br from-violet-100 to-indigo-50",
  },
];

export default function ConnectionsPage() {
  const [states, setStates] = useState<Record<string, ProviderState> | null>(
    null,
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<ProviderRow | null>(null);

  const refresh = async () => {
    setError(null);
    try {
      const r = await fetch(`${API_BASE}/api/providers`);
      if (!r.ok) throw new Error(`GET ${r.status}`);
      const data = (await r.json()) as ProviderState[];
      const map: Record<string, ProviderState> = {};
      for (const p of data) map[p.name] = p;
      setStates(map);
    } catch (e) {
      setError(`Could not load connections: ${(e as Error).message}`);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const signIn = async (row: ProviderRow) => {
    setBusy(row.name);
    setError(null);
    try {
      const r = await fetch(
        `${API_BASE}/api/providers/${row.name}/sign_in_start`,
        { method: "POST" },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(`${r.status}: ${body.detail ?? r.statusText}`);
      }
      setError(
        `Sign-in started for ${row.label}. Browser-driven OAuth lands in a near-term patch — until then state stays "not connected."`,
      );
      window.setTimeout(() => void refresh(), 1500);
    } catch (e) {
      setError(`Could not start sign-in: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async (row: ProviderRow) => {
    setBusy(row.name);
    setError(null);
    try {
      const r = await fetch(
        `${API_BASE}/api/providers/${row.name}/disconnect`,
        { method: "POST" },
      );
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      await refresh();
    } catch (e) {
      setError(`Could not disconnect: ${(e as Error).message}`);
    } finally {
      setBusy(null);
      setConfirmTarget(null);
    }
  };

  return (
    <AppShell title="Personal Space">
      <main className="flex-1 px-gutter-desktop py-12 max-w-5xl mx-auto w-full">
        <div className="mb-12">
          <h1 className="font-display text-display text-on-surface mb-2">
            Connections
          </h1>
          <p className="font-body text-body text-foreground-muted">
            Add the AI assistants you want to use.
          </p>
        </div>

        {error ? (
          <div
            role="alert"
            aria-live="polite"
            className="mb-8 rounded-xl bg-primary/5 border border-primary/10 px-card-padding py-4 font-body text-caption text-on-surface-variant"
          >
            {error}
          </div>
        ) : null}

        <div className="flex flex-col gap-6">
          {PROVIDERS.map((row) => {
            const state = states?.[row.name];
            const active = state?.status === "connected";
            const isBusy = busy === row.name;
            return (
              <div
                key={row.name}
                className="bg-surface p-card-padding rounded-xl shadow-[0_2px_8px_rgba(15,23,42,0.04)] flex items-center justify-between hover:-translate-y-[2px] transition-all duration-300"
              >
                <div className="flex items-center gap-5">
                  <div
                    className={cn(
                      "w-12 h-12 rounded-lg flex items-center justify-center",
                      "font-heading font-semibold text-[18px] text-on-surface",
                      row.swatch,
                    )}
                    aria-hidden
                  >
                    {row.letter}
                  </div>
                  <div>
                    <h3 className="font-heading text-body text-on-surface font-semibold">
                      {row.label}
                    </h3>
                    <p className="font-body text-caption text-foreground-muted">
                      {row.description}
                    </p>
                  </div>
                </div>
                {active ? (
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2 text-success">
                      <div className="w-2 h-2 rounded-full bg-success" />
                      <span className="font-body text-caption">active</span>
                    </div>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => setConfirmTarget(row)}
                      className="font-caption text-caption text-foreground-muted hover:text-on-surface underline-offset-2 hover:underline disabled:opacity-50"
                    >
                      Manage
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void signIn(row)}
                    className="bg-primary hover:bg-primary-container text-on-primary px-5 py-2.5 rounded-xl font-body text-caption font-semibold transition-all active:scale-95 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isBusy ? "Opening…" : "Connect"}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-16 pt-8 border-t border-border flex justify-between items-center">
          <p className="font-body text-caption text-foreground-muted italic">
            A confident surface that responds to intent.
          </p>
        </div>
      </main>

      <Dialog
        open={confirmTarget != null}
        onOpenChange={(open) => !open && setConfirmTarget(null)}
      >
        <DialogContent className="bg-surface rounded-2xl">
          <DialogHeader>
            <DialogTitle className="font-heading text-heading text-on-surface">
              Disconnect {confirmTarget?.label}?
            </DialogTitle>
            <DialogDescription className="font-body text-body text-foreground-muted">
              Future sessions that need {confirmTarget?.label} will prompt
              you to sign in again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setConfirmTarget(null)}
              disabled={busy === confirmTarget?.name}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => confirmTarget && void disconnect(confirmTarget)}
              disabled={busy === confirmTarget?.name}
              className="bg-error text-on-error hover:opacity-90"
            >
              {busy === confirmTarget?.name ? "Working…" : "Disconnect"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
