/**
 * Persistent sidebar navigation.
 *
 * Top section: static routes (Dashboard, Paused, Sessions, New Run).
 * Middle section: live list of projects (fetched from /api/projects),
 * each linkable to /project/?slug=<slug>. Active project highlighted.
 *
 * Routes appear only when their backend exists. Disabled items render
 * with a "soon" badge so the user can see what's coming.
 */
"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Folder,
  FolderPlus,
  LayoutDashboard,
  ListTree,
  PauseCircle,
  PlayCircle,
  ScrollText,
} from "lucide-react";
import { Suspense, useEffect, useState } from "react";

import { useSidebar } from "@/components/layout/sidebar-context";
import { type ProjectResponse, listProjects } from "@/lib/api";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  disabled?: boolean;
}

const PRIMARY_NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/?tab=paused", label: "Paused", icon: PauseCircle },
  { href: "/?tab=recent", label: "Sessions", icon: ListTree },
];

const FOOTER_NAV: NavItem[] = [
  { href: "/run/", label: "New run", icon: PlayCircle },
  { href: "/audit/", label: "Audit log", icon: ScrollText, disabled: true },
];

export function Sidebar() {
  return (
    <Suspense fallback={<SidebarSkeleton />}>
      <SidebarBody />
    </Suspense>
  );
}

function SidebarSkeleton() {
  // Renders nothing on the SSR/static-export pass; the client takes
  // over and shows the real sidebar a tick later. Keeping the
  // <aside> shell would mean duplicating its size class — not worth
  // it for a millisecond flash.
  return null;
}

function SidebarBody() {
  const pathname = usePathname();
  const params = useSearchParams();
  const activeSlug = pathname.startsWith("/project") ? params.get("slug") : null;
  const { collapsed } = useSidebar();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await listProjects();
        if (!cancelled) setProjects(data);
      } catch {
        // ignore — sidebar will just show no project list when backend down
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
    <aside
      className={cn(
        "hidden flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out md:flex",
        collapsed ? "w-14" : "w-60",
      )}
      aria-label="Primary navigation"
    >
      <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-3">
        <span
          aria-hidden
          className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-primary font-bold text-primary-foreground"
        >
          S
        </span>
        {!collapsed && (
          <div className="flex flex-col leading-tight">
            <span className="text-sm font-semibold tracking-tight">
              SelfFork
            </span>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Dashboard
            </span>
          </div>
        )}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-4 text-sm scrollbar-thin">
        {PRIMARY_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={_isActive(item.href, pathname)}
            collapsed={collapsed}
          />
        ))}

        {/* ── Projects section ──────────────────────────────────────── */}
        <div className="pt-3">
          {!collapsed && (
            <div className="mb-1 flex items-center justify-between px-3">
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Projects
              </span>
              <Link
                href="/projects/new/"
                title="Create project"
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                <FolderPlus className="h-3.5 w-3.5" />
              </Link>
            </div>
          )}
          <NavLink
            item={{
              href: "/projects/",
              label: "All projects",
              icon: Folder,
            }}
            active={pathname === "/projects" || pathname === "/projects/"}
            collapsed={collapsed}
          />
          {!collapsed &&
            projects.slice(0, 8).map((p) => (
              <Link
                key={p.slug}
                href={`/project/?slug=${p.slug}`}
                title={p.name}
                className={cn(
                  "ml-2 flex items-center gap-2 rounded-md px-3 py-1.5 text-xs transition-colors",
                  activeSlug === p.slug
                    ? "bg-sidebar-accent text-sidebar-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground",
                )}
              >
                <span aria-hidden className="text-muted-foreground/70">
                  ▸
                </span>
                <span className="truncate">{p.name}</span>
              </Link>
            ))}
        </div>

        <div className="pt-3">
          {FOOTER_NAV.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              active={_isActive(item.href, pathname)}
              collapsed={collapsed}
            />
          ))}
        </div>
      </nav>

      {!collapsed && (
        <div className="border-t border-sidebar-border px-4 py-3 text-[11px] leading-relaxed text-muted-foreground">
          <p className="font-medium text-sidebar-foreground">read-only</p>
          <p>
            UI reflects only on-disk artifacts. No mock data per
            project_ui_stack.md.
          </p>
        </div>
      )}
    </aside>
  );
}

function NavLink({
  item,
  active,
  collapsed,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
}) {
  const Icon = item.icon;
  if (item.disabled) {
    return (
      <span
        title={
          collapsed
            ? `${item.label} — backend endpoint not implemented yet`
            : "Backend endpoint not implemented yet"
        }
        className={cn(
          "flex items-center gap-2.5 rounded-md px-3 py-2 text-muted-foreground opacity-50",
          collapsed && "justify-center px-2",
        )}
      >
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && (
          <>
            <span>{item.label}</span>
            <span className="ml-auto text-[10px] uppercase tracking-wider">
              soon
            </span>
          </>
        )}
      </span>
    );
  }
  return (
    <Link
      href={item.href}
      title={collapsed ? item.label : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-3 py-2 transition-colors",
        active
          ? "bg-sidebar-accent text-sidebar-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground",
        collapsed && "justify-center px-2",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span>{item.label}</span>}
    </Link>
  );
}

function _isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href.split("?")[0]);
}
