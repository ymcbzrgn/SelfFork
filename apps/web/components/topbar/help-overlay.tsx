/**
 * Keyboard-shortcuts help overlay (S8 — ADR-007 §4 S8, operator pick).
 *
 * Self-managed: opens on the global ``selffork:show-shortcuts`` event (the
 * topbar Help button and the command palette both dispatch it) and on the
 * ``?`` key (guarded so typing a literal "?" in an input doesn't trigger it).
 * Every shortcut listed here is verified against the code — no aspirational
 * entries.
 */
"use client";

import { useEffect, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

interface Shortcut {
  keys: string;
  desc: string;
}

const GROUPS: { heading: string; items: Shortcut[] }[] = [
  {
    heading: "Global",
    items: [
      { keys: "⌘K", desc: "Open command palette" },
      { keys: "?", desc: "Show this help" },
      { keys: "[", desc: "Toggle sidebar" },
      { keys: "Esc", desc: "Close dialog / drawer" },
    ],
  },
  {
    heading: "Talk",
    items: [
      { keys: "Enter", desc: "Send message (Shift+Enter = newline)" },
      { keys: "/cli", desc: "Switch CLI for this conversation" },
    ],
  },
  {
    heading: "Workspace",
    items: [
      { keys: "Drag", desc: "Move a Kanban card between columns" },
      { keys: "⌘↵", desc: "Submit the New task dialog" },
      { keys: "type, pause", desc: "Notes auto-save ~0.8s after you stop" },
    ],
  },
];

export function HelpOverlay() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const openHandler = () => setOpen(true);
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key !== "?" || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target?.isContentEditable
      ) {
        return;
      }
      e.preventDefault();
      setOpen(true);
    };
    window.addEventListener("selffork:show-shortcuts", openHandler);
    window.addEventListener("keydown", keyHandler);
    return () => {
      window.removeEventListener("selffork:show-shortcuts", openHandler);
      window.removeEventListener("keydown", keyHandler);
    };
  }, []);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent className="bg-surface text-on-surface border-outline-variant">
        <SheetHeader>
          <SheetTitle className="text-on-surface">Keyboard shortcuts</SheetTitle>
          <SheetDescription className="text-on-surface-variant">
            Everything you can drive from the keyboard.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-2 space-y-5 overflow-y-auto">
          {GROUPS.map((group) => (
            <div key={group.heading}>
              <h3 className="mb-2 text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">
                {group.heading}
              </h3>
              <div className="space-y-1.5">
                {group.items.map((s) => (
                  <div
                    key={`${group.heading}:${s.keys}`}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="text-caption text-on-surface">{s.desc}</span>
                    <kbd className="rounded border border-outline-variant bg-surface-container-high px-2 py-0.5 font-mono text-[11px] text-on-surface-variant">
                      {s.keys}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
