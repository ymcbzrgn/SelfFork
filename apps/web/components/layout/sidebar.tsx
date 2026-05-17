/**
 * SelfFork v3 sidebar.
 *
 * Linear v1 left rail. Five top-level destinations; the Workspaces
 * entry is expandable and lists live projects pulled from
 * `listProjects()`. Active workspace gets a green dot. Footer shows
 * Self Jr's online status + model endpoint slug.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
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
import { listProjects, type ProjectResponse } from "@/lib/api";

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

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((p) => {
        if (!cancelled) setProjects(p);
      })
      .catch(() => {
        /* graceful: empty list */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (inWorkspaces) setOpen(true);
  }, [inWorkspaces]);

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
                  return (
                    <Link
                      key={p.slug}
                      href={`/workspaces/${p.slug}`}
                      className={cn(
                        "py-1 text-caption flex items-center gap-2 transition-colors",
                        active
                          ? "text-on-surface font-medium"
                          : "text-on-surface-variant hover:text-on-surface",
                      )}
                    >
                      {active && (
                        <span className="w-1.5 h-1.5 rounded-full bg-success" />
                      )}
                      <span>{p.name}</span>
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
              <span className="text-success font-bold">● Online</span>
            </span>
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px] text-on-surface-variant">
            <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>gemma-4 @ mac</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
