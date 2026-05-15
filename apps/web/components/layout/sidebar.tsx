/**
 * SelfFork v2 sidebar — Stitch-verbatim port (Workspaces template).
 *
 * Five top-level destinations. Brand block is just two text lines:
 * "SelfFork" + "Creator Space" — no logo experiments. Active state is
 * `text-primary bg-primary/10 font-semibold`. Material Symbols
 * (Stitch default) are substituted for Lucide so we stay on one icon
 * dependency.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FolderOpen,
  Home,
  Link2,
  MessageCircle,
  Settings,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: typeof Home;
}

const NAV: NavItem[] = [
  { href: "/", label: "Home", icon: Home },
  { href: "/workspaces", label: "Workspaces", icon: FolderOpen },
  { href: "/talk", label: "Talk", icon: MessageCircle },
  { href: "/connections", label: "Connections", icon: Link2 },
  { href: "/settings", label: "Settings", icon: Settings },
];

function _isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/" || pathname === "";
  if (pathname.startsWith(href)) return true;
  if (href === "/settings" && pathname.startsWith("/cockpit/settings"))
    return true;
  if (href === "/connections" && pathname.startsWith("/cockpit/providers"))
    return true;
  return false;
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="hidden md:flex w-sidebar-width h-screen fixed left-0 top-0 flex-col py-vertical-gap border-r border-border bg-surface shadow-sm z-50"
      aria-label="Primary navigation"
    >
      <div className="px-6 mb-8">
        <h1 className="font-heading text-heading font-semibold text-on-surface">
          SelfFork
        </h1>
        <p className="font-caption text-caption text-foreground-muted">
          Creator Space
        </p>
      </div>
      <nav className="flex-1 px-3 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = _isActive(href, pathname);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-4 py-2 rounded-lg transition-all duration-200 ease-in-out",
                active
                  ? "text-primary bg-primary/10 font-semibold"
                  : "text-foreground-muted hover:bg-surface-muted",
              )}
            >
              <Icon className="h-5 w-5" strokeWidth={1.75} />
              <span className="font-body text-body">{label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
