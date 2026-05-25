/**
 * SelfFork v3 sidebar.
 *
 * Linear v1 left rail. Five top-level destinations; the Workspaces entry is
 * expandable and lists live projects pulled from `listProjects()`. A "Show
 * archived" toggle re-fetches with archived workspaces included (rendered
 * italic + Archive icon). Active workspace gets a green dot. Footer derives
 * Self Jr's online state from /api/health and the model label from the
 * configured endpoint — no hardcoded values (S8 no-mock).
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
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

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  exact?: boolean;
}

const SECONDARY_NAV: NavItem[] = [
  { href: "/talk", label: "Talk", icon: MessageCircle },
  { href: "/connections", label: "Connections", icon: Link2 },
  { href: "/settings", label: "Settings", icon: Settings },
];

function isActive(pathname: string, href: string, exact = false): boolean {
  if (exact) return pathname === href || pathname === "";
  if (pathname.startsWith(href)) return true;
  if (href === "/connections" && pathname.startsWith("/cockpit/providers")) return true;
  if (href === "/settings" && pathname.startsWith("/cockpit/settings")) return true;
  return false;
}

export function Sidebar() {
  const pathname = usePathname();
  const inWorkspaces = pathname.startsWith("/workspaces");
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [open, setOpen] = useState<boolean>(true);
  const [showArchived, setShowArchived] = useState(false);
  const [online, setOnline] = useState(true);
  const [modelLabel, setModelLabel] = useState<string | null>(null);

  // Workspace list — re-fetch whenever the archived filter flips. The
  // backend ``include_archived`` flag (S7) drives whether archived slugs
  // come back; default off keeps the rail focused on active work.
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

  // Footer model label — the configured endpoint's model name (or an
  // honest "no model endpoint" when none is set). No hardcoded slug.
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
      className="hidden md:flex w-sidebar-width h-screen fixed left-0 top-0 flex-col py-vertical-gap bg-surface-container-low border-r border-outline-variant/30 z-50"
      aria-label="Primary navigation"
    >
      <div className="px-6 mb-8">
        <Link
          href="/"
          className="font-heading text-heading font-semibold text-primary flex items-center gap-2"
        >
          <span className="text-2xl leading-none" aria-hidden>
            ⊕
          </span>
          <span>SelfFork</span>
        </Link>
      </div>

      <nav className="flex-1 space-y-1">
        <Link
          href="/"
          className={cn(
            "rounded-lg mx-2 px-4 py-2 flex items-center gap-3 transition-all",
            isActive(pathname, "/", true)
              ? "bg-primary/[0.08] text-primary font-semibold"
              : "text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/50",
          )}
        >
          <LayoutDashboard className="h-5 w-5" strokeWidth={1.75} />
          <span className="font-body text-body">Dashboard</span>
        </Link>

        <div className="px-2">
          <button
            type="button"
            onClick={() => setOpen((x) => !x)}
            aria-expanded={open}
            className={cn(
              "w-full rounded-lg px-4 py-2 flex items-center justify-between transition-colors",
              inWorkspaces
                ? "bg-primary/[0.08] text-primary font-semibold"
                : "text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/50",
            )}
          >
            <span className="flex items-center gap-3">
              <FolderKanban className="h-5 w-5" strokeWidth={1.75} />
              <span className="font-body text-body">Workspaces</span>
            </span>
            <ChevronDown
              className={cn(
                "h-4 w-4 transition-transform",
                open ? "rotate-0" : "-rotate-90",
              )}
              strokeWidth={1.75}
            />
          </button>
          {open && (
            <div className="mt-1 ml-9 space-y-1 border-l border-outline-variant/40 pl-3">
              {projects.length === 0 ? (
                <p className="py-1 text-caption text-on-surface-variant/70 italic">
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
                        "py-1 text-caption flex items-center gap-2 transition-colors",
                        archived && "italic opacity-60",
                        active
                          ? "text-on-surface font-medium"
                          : "text-on-surface-variant hover:text-on-surface",
                      )}
                    >
                      {active && (
                        <span className="w-1.5 h-1.5 rounded-full bg-success" />
                      )}
                      <span className="truncate">{p.name}</span>
                      {archived && (
                        <Archive
                          className="h-3 w-3 ml-auto text-on-surface-variant"
                          strokeWidth={1.75}
                        />
                      )}
                    </Link>
                  );
                })
              )}
              <Link
                href="/talk?intent=new-workspace"
                className="py-1 text-primary text-caption font-semibold flex items-center gap-1 hover:underline"
              >
                <Plus className="h-3 w-3" strokeWidth={2} />
                <span>New project</span>
              </Link>
              <div className="flex items-center justify-between pt-1">
                <label
                  htmlFor="show-archived"
                  className="flex items-center gap-1.5 text-[10px] text-on-surface-variant/70 cursor-pointer"
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

        {SECONDARY_NAV.map(({ href, label, icon: Icon, exact }) => {
          const active = isActive(pathname, href, exact);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "rounded-lg mx-2 px-4 py-2 flex items-center gap-3 transition-all",
                active
                  ? "bg-primary/[0.08] text-primary font-semibold"
                  : "text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/50",
              )}
            >
              <Icon className="h-5 w-5" strokeWidth={1.75} />
              <span className="font-body text-body">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="px-4 mt-auto">
        <div className="bg-surface-container rounded-xl p-3 space-y-2 border border-outline-variant/20">
          <div className="flex items-center gap-2 font-mono text-[11px] text-on-surface-variant">
            <Cpu className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>
              Self Jr ·{" "}
              <span
                className={cn(
                  "font-bold",
                  online ? "text-success" : "text-error",
                )}
              >
                ● {online ? "Online" : "Offline"}
              </span>
            </span>
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px] text-on-surface-variant">
            <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span className="truncate">{modelLabel ?? "no model endpoint"}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
