/**
 * SelfFork v3 topbar.
 *
 * Sticky header above the main column. Left: page title with optional
 * dropdown indicator. Center: Cmd+K search affordance. Right:
 * notification bell + Live indicator + system status + help + operator
 * marker. Backend health is polled every 15s; the Live pill flips to
 * "Offline" when /api/health fails.
 */
"use client";

import { useEffect, useState } from "react";
import {
  Bell,
  ChevronDown,
  HelpCircle,
  Search,
  ServerCog,
} from "lucide-react";

import { getHealth, getPendingConfirmationCount } from "@/lib/api";

interface TopBarProps {
  /** Page title shown on the left. Defaults to "Dashboard". */
  title?: string;
}

export function TopBar({ title = "Dashboard" }: TopBarProps) {
  const [online, setOnline] = useState(true);
  // S3 Phase F — real pending count from /api/pending-confirmations/count.
  // 10-second poll matches the destructive-action human-scale tempo.
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        await getHealth();
        if (!cancelled) setOnline(true);
      } catch {
        if (!cancelled) setOnline(false);
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const count = await getPendingConfirmationCount();
        if (!cancelled) setPendingCount(count);
      } catch {
        // Best-effort — the badge falls back to 0 on any backend error.
        if (!cancelled) setPendingCount(0);
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <header
      className="h-topbar-height w-full sticky top-0 z-40 bg-surface-container-lowest border-b border-outline-variant/20 flex items-center justify-between px-gutter-desktop"
      aria-label="Top navigation"
    >
      <div className="flex items-center gap-8 min-w-0">
        <button
          type="button"
          className="flex items-center gap-2 font-heading text-body font-bold text-on-surface group whitespace-nowrap"
          aria-label="Switch workspace"
        >
          <span className="truncate">{title}</span>
          <ChevronDown
            className="h-4 w-4 transition-transform group-hover:translate-y-0.5"
            strokeWidth={1.75}
          />
        </button>
        <div className="relative w-72 max-w-[40vw] hidden md:block">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-on-surface-variant"
            strokeWidth={1.75}
          />
          <input
            type="text"
            placeholder="Search… ⌘K"
            className="w-full bg-surface-container-high/50 border-none rounded-full pl-10 pr-4 py-1.5 text-caption focus:ring-2 focus:ring-primary/20 placeholder:text-on-surface-variant outline-none"
            aria-label="Global search (command palette)"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          className="p-2 hover:bg-surface-container-high/50 transition-colors rounded-full relative"
          aria-label={
            pendingCount
              ? `Notifications, ${pendingCount} pending`
              : "Notifications"
          }
        >
          <Bell
            className="h-5 w-5 text-on-surface-variant"
            strokeWidth={1.75}
          />
          {pendingCount > 0 && (
            <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 bg-error text-white text-[10px] flex items-center justify-center rounded-full font-bold tabular-nums">
              {pendingCount}
            </span>
          )}
        </button>

        <div
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full ${
            online ? "" : "opacity-60"
          }`}
          aria-live="polite"
        >
          <span
            className={`w-2 h-2 rounded-full ${
              online ? "bg-error animate-pulse-red" : "bg-on-surface-variant"
            }`}
            aria-hidden
          />
          <span className="text-caption font-bold text-on-surface-variant">
            {online ? "Live" : "Offline"}
          </span>
        </div>

        <button
          type="button"
          className="p-2 hover:bg-surface-container-high/50 transition-colors rounded-full"
          aria-label="System status"
        >
          <ServerCog
            className="h-5 w-5 text-on-surface-variant"
            strokeWidth={1.75}
          />
        </button>

        <button
          type="button"
          className="p-2 hover:bg-surface-container-high/50 transition-colors rounded-full"
          aria-label="Help and keyboard shortcuts"
        >
          <HelpCircle
            className="h-5 w-5 text-on-surface-variant"
            strokeWidth={1.75}
          />
        </button>

        <div
          aria-label="Local operator"
          className="ml-2 w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-caption text-caption font-semibold"
        >
          ·
        </div>
      </div>
    </header>
  );
}
