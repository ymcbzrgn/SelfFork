/**
 * Top bar: shows backend connectivity + audit paths so the user knows
 * which on-disk artifacts the dashboard is reading from. Polls
 * /api/health every 10s; switches to a clear "offline" state when the
 * backend goes away.
 */
"use client";

import {
  CircleHelp,
  FolderOpen,
  PanelLeft,
  PanelLeftClose,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useState } from "react";

import { useSidebar } from "@/components/layout/sidebar-context";
import { type DashboardHealth, getHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

type HealthState =
  | { status: "loading" }
  | { status: "online"; data: DashboardHealth }
  | { status: "offline"; error: string };

export function TopBar({ title }: { title: string }) {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });
  const { collapsed, toggle } = useSidebar();

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await getHealth();
        if (!cancelled) setHealth({ status: "online", data });
      } catch (e) {
        if (!cancelled) {
          setHealth({
            status: "offline",
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

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4 md:px-6">
      <button
        type="button"
        onClick={toggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="hidden h-8 w-8 items-center justify-center rounded-md border border-transparent text-muted-foreground transition-colors hover:border-border hover:text-foreground md:inline-flex"
      >
        {collapsed ? (
          <PanelLeft className="h-4 w-4" />
        ) : (
          <PanelLeftClose className="h-4 w-4" />
        )}
      </button>

      <h1 className="truncate text-base font-semibold tracking-tight">
        {title}
      </h1>

      <div className="ml-auto flex items-center gap-3 text-xs">
        <PathPill label="audit" path={pathFromHealth(health, "audit_dir")} />
        <PathPill
          label="scheduled"
          path={pathFromHealth(health, "resume_dir")}
        />
        <ConnectivityPill state={health} />
      </div>
    </header>
  );
}

function PathPill({ label, path }: { label: string; path: string | null }) {
  if (path === null) {
    return (
      <span className="hidden items-center gap-1.5 text-muted-foreground lg:inline-flex">
        <FolderOpen className="h-3.5 w-3.5" />
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
        <span className="font-mono">…</span>
      </span>
    );
  }
  return (
    <span
      title={path}
      className="hidden items-center gap-1.5 text-muted-foreground lg:inline-flex"
    >
      <FolderOpen className="h-3.5 w-3.5" />
      <span className="text-[10px] uppercase tracking-wider">{label}</span>
      <span className="max-w-[18ch] truncate font-mono">{shortenPath(path)}</span>
    </span>
  );
}

function ConnectivityPill({ state }: { state: HealthState }) {
  if (state.status === "loading") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1">
        <CircleHelp className="h-3.5 w-3.5 text-muted-foreground" />
        <span>connecting</span>
      </span>
    );
  }
  if (state.status === "online") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
          "border-success/40 bg-success/10 text-success",
        )}
      >
        <Wifi className="h-3.5 w-3.5" />
        <span>online</span>
      </span>
    );
  }
  return (
    <span
      title={state.error}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
        "border-destructive/40 bg-destructive/10 text-destructive",
      )}
    >
      <WifiOff className="h-3.5 w-3.5" />
      <span>offline</span>
    </span>
  );
}

function pathFromHealth(state: HealthState, key: keyof DashboardHealth): string | null {
  if (state.status !== "online") return null;
  return state.data[key] as string;
}

function shortenPath(p: string): string {
  // Replace the user's home directory with ~ for legibility, then
  // collapse any leading ``/Users/<name>`` so the topbar stays compact
  // even on screens that aren't full-width.
  const homeMatch = p.match(/^\/(?:Users|home)\/([^/]+)/);
  if (!homeMatch) return p;
  return p.replace(homeMatch[0], "~");
}
