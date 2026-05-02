/**
 * Global command palette — opened with ⌘K / Ctrl+K from anywhere in
 * the app. Built on cmdk (Linear / Raycast pattern). Surfaces every
 * navigation route plus the live project list, so the operator never
 * has to leave the keyboard.
 *
 * Future: action commands (kanban_card_move via tool registry, send
 * message to active CLI, switch CLI rotation) — wired once the
 * frontend can dispatch tool calls back to FastAPI.
 */
"use client";

import { Command } from "cmdk";
import {
  Folder,
  FolderPlus,
  KeyboardIcon,
  LayoutDashboard,
  ListTree,
  PauseCircle,
  PlayCircle,
  Search,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { listProjects, type ProjectResponse } from "@/lib/api";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const router = useRouter();

  // ⌘K / Ctrl+K toggles the palette globally. Esc closes (cmdk handles).
  // Buttons elsewhere (e.g. topbar) dispatch ``selffork:open-palette``
  // to open programmatically.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    const openHandler = () => setOpen(true);
    window.addEventListener("keydown", keyHandler);
    window.addEventListener("selffork:open-palette", openHandler);
    return () => {
      window.removeEventListener("keydown", keyHandler);
      window.removeEventListener("selffork:open-palette", openHandler);
    };
  }, []);

  // Refetch projects each time the palette opens — cheap, keeps the
  // list fresh without a background poll firing on every page.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void listProjects()
      .then((data) => {
        if (!cancelled) setProjects(data);
      })
      .catch(() => {
        // Backend offline — palette still works for navigation.
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      className="fixed inset-0 z-50 grid place-items-start bg-black/50 px-4 pt-[15vh] backdrop-blur-sm"
    >
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <Command.Input
            autoFocus
            placeholder="Search projects, sessions, actions…"
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            esc
          </kbd>
        </div>

        <Command.List className="max-h-[60vh] overflow-y-auto p-2 scrollbar-thin">
          <Command.Empty className="px-3 py-8 text-center text-sm text-muted-foreground">
            No results.
          </Command.Empty>

          <PaletteGroup heading="Navigate">
            <PaletteItem icon={LayoutDashboard} label="Dashboard" onSelect={() => go("/")} />
            <PaletteItem icon={PauseCircle} label="Paused sessions" onSelect={() => go("/?tab=paused")} />
            <PaletteItem icon={ListTree} label="Recent sessions" onSelect={() => go("/?tab=recent")} />
            <PaletteItem icon={Folder} label="All projects" onSelect={() => go("/projects/")} />
          </PaletteGroup>

          {projects.length > 0 && (
            <PaletteGroup heading="Projects">
              {projects.map((p) => (
                <PaletteItem
                  key={p.slug}
                  icon={Folder}
                  label={p.name}
                  hint={p.slug}
                  onSelect={() => go(`/project/?slug=${p.slug}`)}
                />
              ))}
            </PaletteGroup>
          )}

          <PaletteGroup heading="Actions">
            <PaletteItem icon={FolderPlus} label="New project" onSelect={() => go("/projects/new/")} />
            <PaletteItem icon={PlayCircle} label="New run" onSelect={() => go("/run/")} />
            <PaletteItem
              icon={KeyboardIcon}
              label="Keyboard shortcuts"
              hint="?"
              onSelect={() => {
                setOpen(false);
                if (typeof window !== "undefined") {
                  window.dispatchEvent(new Event("selffork:show-shortcuts"));
                }
              }}
            />
          </PaletteGroup>
        </Command.List>

        <div className="flex items-center gap-3 border-t border-border bg-muted/40 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground">
          <span>↑↓ navigate</span>
          <span>↵ select</span>
          <span>esc close</span>
        </div>
      </div>
    </Command.Dialog>
  );
}

function PaletteGroup({
  heading,
  children,
}: {
  heading: string;
  children: React.ReactNode;
}) {
  // Heading-only styling (uppercase + muted) applied via descendant
  // selector so item labels stay normal case.
  return (
    <Command.Group
      heading={heading}
      className="px-1 py-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground"
    >
      {children}
    </Command.Group>
  );
}

function PaletteItem({
  icon: Icon,
  label,
  hint,
  onSelect,
}: {
  icon: LucideIcon;
  label: string;
  hint?: string;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-2.5 rounded-md px-3 py-2 text-sm text-foreground aria-selected:bg-sidebar-accent aria-selected:text-sidebar-foreground"
    >
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="flex-1 truncate">{label}</span>
      {hint && (
        <span className="font-mono text-[11px] text-muted-foreground">{hint}</span>
      )}
    </Command.Item>
  );
}
