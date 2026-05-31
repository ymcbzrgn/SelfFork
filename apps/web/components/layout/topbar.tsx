/**
 * SelfFork v3 topbar.
 *
 * Sticky header above the main column. Left: page-title dropdown (page-
 * specific actions) + a Cmd+K search affordance. Right: notification bell
 * (opens the pending-confirmations drawer), Live indicator, system-status
 * drawer, help overlay, operator marker. Backend health is polled every
 * 15s; the Live pill flips to "Offline" when /api/health fails.
 *
 * S8 (ADR-007 §4 S8): every control here is wired — no dead buttons. The
 * title dropdown is driven by the current route (usePathname); workspace
 * actions dispatch ``selffork:workspace:*`` events the workspace page
 * listens for, so the topbar stays decoupled from per-page state.
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Archive,
  ArrowLeftRight,
  Bell,
  ChevronDown,
  Command,
  HelpCircle,
  Keyboard,
  MessageSquarePlus,
  PauseCircle,
  Pencil,
  RefreshCw,
  Search,
  ServerCog,
  type LucideIcon,
} from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { HelpOverlay } from "@/components/topbar/help-overlay";
import { PendingSheet } from "@/components/topbar/pending-sheet";
import { SystemStatusSheet } from "@/components/topbar/system-status";
import { getHealth, getPendingConfirmationCount } from "@/lib/api";

interface TopBarProps {
  /** Page title shown on the left. Defaults to "Dashboard". */
  title?: string;
}

interface TitleAction {
  label: string;
  icon: LucideIcon;
  onSelect: () => void;
}

function fire(name: string): void {
  window.dispatchEvent(new Event(name));
}

export function TopBar({ title = "Dashboard" }: TopBarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [online, setOnline] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  const [statusOpen, setStatusOpen] = useState(false);
  const [pendingOpen, setPendingOpen] = useState(false);

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

  const refreshPendingCount = useCallback(async () => {
    try {
      setPendingCount(await getPendingConfirmationCount());
    } catch {
      // Best-effort — the badge falls back to its last value on error.
    }
  }, []);

  useEffect(() => {
    void refreshPendingCount();
    // 10-second poll matches the destructive-action human-scale tempo.
    const id = window.setInterval(() => void refreshPendingCount(), 10_000);
    return () => window.clearInterval(id);
  }, [refreshPendingCount]);

  // Title-dropdown actions for the current route. Universal actions
  // (palette, shortcuts) are always present; route-specific ones lead.
  const actions = useMemo<TitleAction[]>(() => {
    const universal: TitleAction[] = [
      {
        label: "Open command palette",
        icon: Command,
        onSelect: () => fire("selffork:open-palette"),
      },
      {
        label: "Keyboard shortcuts",
        icon: Keyboard,
        onSelect: () => fire("selffork:show-shortcuts"),
      },
    ];
    if (pathname.startsWith("/workspaces/")) {
      return [
        {
          label: "Switch workspace",
          icon: ArrowLeftRight,
          onSelect: () => fire("selffork:workspace:switch"),
        },
        {
          label: "Edit this workspace",
          icon: Pencil,
          onSelect: () => fire("selffork:workspace:edit"),
        },
        {
          label: "Pause / resume Self Jr",
          icon: PauseCircle,
          onSelect: () => fire("selffork:workspace:pause"),
        },
        {
          label: "Archive workspace",
          icon: Archive,
          onSelect: () => fire("selffork:workspace:archive"),
        },
        ...universal,
      ];
    }
    if (pathname.startsWith("/talk")) {
      return [
        {
          label: "New conversation",
          icon: MessageSquarePlus,
          onSelect: () => router.push("/talk?intent=new-workspace"),
        },
        ...universal,
      ];
    }
    if (pathname.startsWith("/connections")) {
      return [
        {
          label: "Refresh quotas",
          icon: RefreshCw,
          onSelect: () => window.location.reload(),
        },
        ...universal,
      ];
    }
    if (pathname.startsWith("/settings")) {
      return [
        {
          label: "Reload settings",
          icon: RefreshCw,
          onSelect: () => window.location.reload(),
        },
        ...universal,
      ];
    }
    // Dashboard + any other route.
    return [
      {
        label: "Reload data",
        icon: RefreshCw,
        onSelect: () => window.location.reload(),
      },
      ...universal,
    ];
  }, [pathname, router]);

  return (
    <header
      className="h-topbar-height w-full sticky top-0 z-40 bg-surface-container-lowest border-b border-outline-variant/20 flex items-center justify-between px-gutter-desktop"
      aria-label="Top navigation"
    >
      <div className="flex items-center gap-8 min-w-0">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-2 font-heading text-body font-bold text-on-surface group whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded"
              aria-label="Page actions"
            >
              <span className="truncate">{title}</span>
              <ChevronDown
                className="h-4 w-4 transition-transform group-data-[state=open]:rotate-180"
                strokeWidth={1.75}
              />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            className="bg-surface text-on-surface border-outline-variant w-56"
          >
            {actions.map((action) => (
              <DropdownMenuItem
                key={action.label}
                onSelect={action.onSelect}
                className="flex items-center gap-2 text-caption cursor-pointer"
              >
                <action.icon
                  className="h-4 w-4 text-on-surface-variant"
                  strokeWidth={1.75}
                />
                {action.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <button
          type="button"
          onClick={() => fire("selffork:open-palette")}
          className="relative w-72 max-w-[40vw] hidden md:flex items-center text-left outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-full"
          aria-label="Open command palette"
        >
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-on-surface-variant"
            strokeWidth={1.75}
          />
          <span className="w-full bg-surface-container-high/50 rounded-full pl-10 pr-4 py-1.5 text-caption text-on-surface-variant">
            Search… ⌘K
          </span>
        </button>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setPendingOpen(true)}
          className="p-2 hover:bg-surface-container-high/50 transition-colors rounded-full relative outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
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
          onClick={() => setStatusOpen(true)}
          className="p-2 hover:bg-surface-container-high/50 transition-colors rounded-full outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          aria-label="System status"
        >
          <ServerCog
            className="h-5 w-5 text-on-surface-variant"
            strokeWidth={1.75}
          />
        </button>

        <button
          type="button"
          onClick={() => fire("selffork:show-shortcuts")}
          className="p-2 hover:bg-surface-container-high/50 transition-colors rounded-full outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
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

      <SystemStatusSheet open={statusOpen} onOpenChange={setStatusOpen} />
      <PendingSheet
        open={pendingOpen}
        onOpenChange={setPendingOpen}
        onResolved={() => void refreshPendingCount()}
      />
      <HelpOverlay />
    </header>
  );
}
