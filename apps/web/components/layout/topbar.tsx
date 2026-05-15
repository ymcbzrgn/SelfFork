/**
 * SelfFork v2 topbar — Stitch-verbatim port.
 *
 * surface background (one tonal step above the page), heading-typed
 * workspace title on the left, a small primary-container avatar on the
 * right. No search, no audit-dir pills. Backend health is polled
 * silently — only when /api/health drops do we surface a subtle hint.
 */
"use client";

import { useEffect, useState } from "react";

import { getHealth } from "@/lib/api";

interface TopBarProps {
  /** Title displayed left — falls back to the default workspace label. */
  title?: string;
}

export function TopBar({ title = "Personal Space" }: TopBarProps) {
  const [online, setOnline] = useState(true);

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

  return (
    <header className="h-topbar-height w-full sticky top-0 z-40 bg-surface flex items-center justify-between px-gutter-desktop">
      <div className="flex items-center gap-3">
        <h2 className="font-heading text-heading font-semibold text-on-surface">
          {title}
        </h2>
        {!online ? (
          <span
            className="font-caption text-caption font-semibold text-tertiary uppercase tracking-wider"
            aria-label="backend offline"
          >
            offline
          </span>
        ) : null}
      </div>
      <div className="flex items-center gap-4">
        {/* No auth/user system yet — soft primary marker. */}
        <span
          aria-label="Local instance"
          className="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-caption text-caption font-semibold"
        >
          ·
        </span>
      </div>
    </header>
  );
}
