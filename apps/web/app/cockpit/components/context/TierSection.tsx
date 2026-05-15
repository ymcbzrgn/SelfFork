/**
 * Generic collapsible per-tier section — Order 9.
 *
 * Header shows the tier name + note count + last-updated chip;
 * children render below when expanded. Plain ``<details>`` element so
 * keyboard / screen-reader semantics come for free.
 */
"use client";

import type { MindTier } from "@/lib/store";
import { useCockpitStore } from "@/lib/store";

interface Props {
  tier: MindTier;
  title: string;
  count: number;
  lastUpdated: string | null;
  children: React.ReactNode;
}

export function TierSection({
  tier,
  title,
  count,
  lastUpdated,
  children,
}: Props) {
  const expanded = useCockpitStore((s) => s.contextExpandedTiers).has(tier);
  const toggle = useCockpitStore((s) => s.toggleContextTier);
  return (
    <details
      open={expanded}
      onToggle={(e) => {
        const open = (e.currentTarget as HTMLDetailsElement).open;
        if (open !== expanded) toggle(tier);
      }}
      className="rounded-md border border-border/60 bg-card/40"
      data-testid={`tier-section-${tier}`}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase text-muted-foreground">
            {tier.replace("_", " ")}
          </span>
          <span className="font-medium">{title}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span data-testid={`tier-count-${tier}`}>{count} notes</span>
          {lastUpdated ? (
            <time>{lastUpdated.slice(0, 19)}</time>
          ) : (
            <span>—</span>
          )}
        </div>
      </summary>
      <div className="border-t border-border/40 p-3 text-sm">{children}</div>
    </details>
  );
}
