/**
 * SelfFork Jr sidebar — "quiet instrument" left rail.
 *
 * Grouped nav (Watch / Work / System). The Workspaces entry is expandable and
 * lists live projects from `listProjects()`. Footer derives Self Jr's online
 * state from /api/health and the model label from the configured endpoint —
 * no hardcoded values (S8 no-mock). Data wiring preserved; presentation
 * reskinned to the calm celadon/porcelain design language.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import {
  Archive,
  ChevronDown,
  Cpu,
  CheckCircle2,
  FolderKanban,
  LayoutDashboard,
  Link2,
  MessageCircle,
  Plus,
  Settings,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
import {
  getHealth,
  getModelEndpoint,
  listProjects,
  type ProjectResponse,
} from "@/lib/api";

function isActive(pathname: string, href: string, exact = false): boolean {
  if (exact) return pathname === href || pathname === "";
  if (pathname.startsWith(href)) return true;
  if (href === "/connections" && pathname.startsWith("/cockpit/providers")) return true;
  if (href === "/settings" && pathname.startsWith("/cockpit/settings")) return true;
  return false;
}

const NAV_ITEM =
  "group relative flex items-center gap-3 rounded-md px-3 py-2 text-[13.5px] transition-colors";
const NAV_ON =
  "bg-accent text-primary font-semibold before:content-[''] before:absolute before:left-0 before:top-2 before:bottom-2 before:w-[3px] before:rounded-full before:bg-primary";
const NAV_OFF = "text-muted-foreground hover:bg-secondary hover:text-foreground";

function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/70">
      {children}
    </p>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const inWorkspaces = pathname.startsWith("/workspaces");
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [open, setOpen] = useState<boolean>(true);
  const [showArchived, setShowArchived] = useState(false);
  const [online, setOnline] = useState(true);
  const [modelLabel, setModelLabel] = useState<string | null>(null);

  // Workspace list — re-fetch whenever the archived filter flips (S7).
  useEffect(() => {
    let cancelled = false;
    listProjects({ include_archived: showArchived })
      .then((p) => {
        if (!cancelled) setProjects(p);
      })
      .catch(() => {
        /* graceful: empty list */
      });
    return () => {
      cancelled = true;
    };
  }, [showArchived]);

  useEffect(() => {
    if (inWorkspaces) setOpen(true);
  }, [inWorkspaces]);

  // Footer health — poll /api/health every 15s (matches the topbar pill).
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

  // Footer model label — the configured endpoint's model name (no hardcode).
  useEffect(() => {
    let cancelled = false;
    getModelEndpoint()
      .then((m) => {
        if (!cancelled) setModelLabel(m.model_name || null);
      })
      .catch(() => {
        if (!cancelled) setModelLabel(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <aside
      className="hidden md:flex w-sidebar-width h-screen fixed left-0 top-0 flex-col bg-sidebar border-r border-border z-50"
      aria-label="Primary navigation"
    >
      {/* brand */}
      <div className="flex items-center gap-3 px-5 pt-5 pb-4 border-b border-border/60">
        <svg
          width="28"
          height="28"
          viewBox="0 0 30 30"
          fill="none"
          aria-hidden
          className="shrink-0"
        >
          <circle cx="15" cy="15" r="14" className="stroke-primary" strokeWidth="1.3" opacity="0.32" />
          <path
            d="M15 6 L15 13 M15 13 L9 19 M15 13 L21 19"
            className="stroke-primary"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="15" cy="6" r="2" className="fill-primary" />
          <circle cx="9" cy="19" r="2" className="fill-primary" />
          <circle cx="21" cy="19" r="2" className="fill-primary" />
        </svg>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold leading-tight">
            SelfFork <span className="text-primary">Jr</span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
            heartbeat active
          </div>
        </div>
      </div>

      {/* nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-4 space-y-5">
        <div>
          <GroupLabel>Watch</GroupLabel>
          <Link
            href="/"
            className={cn(NAV_ITEM, isActive(pathname, "/", true) ? NAV_ON : NAV_OFF)}
          >
            <LayoutDashboard className="h-[18px] w-[18px]" strokeWidth={1.75} />
            <span>Dashboard</span>
          </Link>
        </div>

        <div>
          <GroupLabel>Work</GroupLabel>
          <div>
            <button
              type="button"
              onClick={() => setOpen((x) => !x)}
              aria-expanded={open}
              className={cn(NAV_ITEM, "w-full justify-between", inWorkspaces ? NAV_ON : NAV_OFF)}
            >
              <span className="flex items-center gap-3">
                <FolderKanban className="h-[18px] w-[18px]" strokeWidth={1.75} />
                <span>Workspaces</span>
              </span>
              <ChevronDown
                className={cn("h-4 w-4 transition-transform", open ? "rotate-0" : "-rotate-90")}
                strokeWidth={1.75}
              />
            </button>
            {open && (
              <div className="mt-1 ml-8 space-y-0.5 border-l border-border pl-3">
                {projects.length === 0 ? (
                  <p className="py-1 text-[12px] italic text-muted-foreground/70">
                    no workspaces yet
                  </p>
                ) : (
                  projects.map((p) => {
                    const active = pathname === `/workspaces/${p.slug}`;
                    const archived = p.archived_at !== null;
                    return (
                      <Link
                        key={p.slug}
                        href={`/workspaces/${p.slug}`}
                        className={cn(
                          "flex items-center gap-2 py-1 text-[12.5px] transition-colors",
                          archived && "italic opacity-60",
                          active
                            ? "text-foreground font-medium"
                            : "text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {active && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
                        <span className="truncate">{p.name}</span>
                        {archived && (
                          <Archive className="ml-auto h-3 w-3 text-muted-foreground" strokeWidth={1.75} />
                        )}
                      </Link>
                    );
                  })
                )}
                <Link
                  href="/talk?intent=new-workspace"
                  className="flex items-center gap-1 py-1 text-[12.5px] font-semibold text-primary hover:underline"
                >
                  <Plus className="h-3 w-3" strokeWidth={2} />
                  <span>New project</span>
                </Link>
                <div className="flex items-center justify-between pt-1">
                  <label
                    htmlFor="show-archived"
                    className="flex cursor-pointer items-center gap-1.5 text-[10px] text-muted-foreground/70"
                  >
                    <Archive className="h-3 w-3" strokeWidth={1.75} />
                    Show archived
                  </label>
                  <Switch
                    id="show-archived"
                    checked={showArchived}
                    onCheckedChange={setShowArchived}
                    className="scale-75"
                  />
                </div>
              </div>
            )}
          </div>
          <Link
            href="/talk"
            className={cn(NAV_ITEM, isActive(pathname, "/talk") ? NAV_ON : NAV_OFF)}
          >
            <MessageCircle className="h-[18px] w-[18px]" strokeWidth={1.75} />
            <span>Talk</span>
          </Link>
        </div>

        <div>
          <GroupLabel>System</GroupLabel>
          <Link
            href="/connections"
            className={cn(NAV_ITEM, isActive(pathname, "/connections") ? NAV_ON : NAV_OFF)}
          >
            <Link2 className="h-[18px] w-[18px]" strokeWidth={1.75} />
            <span>Connections</span>
          </Link>
          <Link
            href="/settings"
            className={cn(NAV_ITEM, isActive(pathname, "/settings") ? NAV_ON : NAV_OFF)}
          >
            <Settings className="h-[18px] w-[18px]" strokeWidth={1.75} />
            <span>Settings</span>
          </Link>
        </div>
      </nav>

      {/* footer */}
      <div className="border-t border-border/60 px-4 pt-3 pb-2 space-y-2.5">
        <div className="flex items-center gap-2.5">
          <div className="grid h-6 w-6 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
            Y
          </div>
          <div className="text-[12.5px] leading-tight">
            Yamaç
            <span className="block text-[10.5px] text-muted-foreground">operator</span>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary px-2.5 py-1 text-[11px] text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          Autonomy · Guided
        </span>
        <div className="space-y-1 rounded-lg border border-border/60 bg-card p-2.5">
          <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
            <Cpu className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>
              Self Jr ·{" "}
              <span className={cn("font-semibold", online ? "text-primary" : "text-destructive")}>
                {online ? "online" : "offline"}
              </span>
            </span>
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span className="truncate">{modelLabel ?? "no model endpoint"}</span>
          </div>
        </div>
        <div className="text-[9.5px] font-medium uppercase tracking-[0.15em] text-muted-foreground/70">
          Beni tanısın yeter
        </div>
      </div>
    </aside>
  );
}
