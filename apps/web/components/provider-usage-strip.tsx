/**
 * Provider usage strip — one card per CLI agent the user has actually
 * used (per ``project_provider_usage_source.md``: never fabricated
 * "0 calls" rows for unused providers).
 *
 * Reads ``GET /api/usage/providers`` every 10s. When the endpoint
 * returns an empty array (no audit log evidence yet), we render a
 * single hint card pointing the user at ``selffork run`` so they
 * understand the strip will populate after the first invocation.
 */
"use client";

import { Activity, Clock, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { type ProviderUsage, listProviderUsage } from "@/lib/api";
import { cn } from "@/lib/utils";

type State =
  | { status: "loading" }
  | { status: "ok"; data: ProviderUsage[] }
  | { status: "error"; error: string };

export function ProviderUsageStrip() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await listProviderUsage();
        if (!cancelled) setState({ status: "ok", data });
      } catch (e) {
        if (!cancelled) {
          setState({
            status: "error",
            error: e instanceof Error ? e.message : String(e),
          });
        }
      }
    };
    void poll();
    const t = setInterval(() => void poll(), 10_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  if (state.status === "loading") {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-4">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-border bg-card"
          />
        ))}
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
        Couldn't load provider usage: {state.error}
      </div>
    );
  }
  if (state.data.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-6 text-center">
        <p className="text-sm font-medium">No provider activity yet</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Run <code className="font-mono">selffork run &lt;prd&gt;</code>{" "}
          to populate this strip — counts come straight from your audit log.
        </p>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-4">
      {state.data.map((row) => (
        <ProviderCard key={row.cli_agent} usage={row} />
      ))}
    </div>
  );
}

function ProviderCard({ usage }: { usage: ProviderUsage }) {
  const { cli_agent, window_label, calls_in_window, next_reset_at } = usage;
  const tone = _toneFor(cli_agent);
  return (
    <div
      className={cn(
        "rounded-lg border p-4 shadow-sm",
        tone === "claude" && "border-orange-500/30 bg-orange-500/5",
        tone === "gemini" && "border-blue-500/30 bg-blue-500/5",
        tone === "opencode" && "border-purple-500/30 bg-purple-500/5",
        tone === "codex" && "border-emerald-500/30 bg-emerald-500/5",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {cli_agent}
        </span>
        <Activity className={cn("h-4 w-4", _iconColor(tone))} />
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold tabular-nums tracking-tight">
          {calls_in_window}
        </span>
        <span className="text-xs text-muted-foreground">
          calls in last {window_label}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {next_reset_at ? (
          <>
            <Clock className="h-3 w-3" />
            <span>
              resets <ResetCountdown isoTs={next_reset_at} />
            </span>
          </>
        ) : (
          <>
            <RefreshCcw className="h-3 w-3" />
            <span>no rate-limit observed</span>
          </>
        )}
      </div>
    </div>
  );
}

function ResetCountdown({ isoTs }: { isoTs: string }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  if (now === null) return <span>…</span>;
  const diffSec = Math.floor((new Date(isoTs).getTime() - now.getTime()) / 1000);
  if (diffSec <= 0) return <span title={isoTs}>now</span>;
  if (diffSec < 60) return <span title={isoTs}>in {diffSec}s</span>;
  if (diffSec < 3600) return <span title={isoTs}>in {Math.floor(diffSec / 60)}m</span>;
  if (diffSec < 86400)
    return <span title={isoTs}>in {Math.floor(diffSec / 3600)}h</span>;
  return <span title={isoTs}>in {Math.floor(diffSec / 86400)}d</span>;
}

function _toneFor(cli: ProviderUsage["cli_agent"]): string {
  if (cli === "claude-code") return "claude";
  if (cli === "gemini-cli") return "gemini";
  if (cli === "codex") return "codex";
  return "opencode";
}

function _iconColor(tone: string): string {
  if (tone === "claude") return "text-orange-500";
  if (tone === "gemini") return "text-blue-500";
  if (tone === "codex") return "text-emerald-500";
  return "text-purple-500";
}
