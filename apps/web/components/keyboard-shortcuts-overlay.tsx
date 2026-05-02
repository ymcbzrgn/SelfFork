/**
 * `?` opens an overlay listing every keyboard shortcut. Linear-style
 * discoverability: Yamaç doesn't need to remember bindings, just
 * press `?` and read.
 *
 * The list mirrors the bindings actually wired in the app — when a
 * new shortcut lands somewhere, add the row here too. This is the
 * one source operators check, so it must not lie.
 */
"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";

interface Shortcut {
  keys: string[];
  description: string;
}

interface ShortcutGroup {
  heading: string;
  items: Shortcut[];
}

const GROUPS: ShortcutGroup[] = [
  {
    heading: "Global",
    items: [
      { keys: ["⌘", "K"], description: "Open command palette" },
      { keys: ["?"], description: "Show this overlay" },
      { keys: ["["], description: "Toggle sidebar" },
      { keys: ["esc"], description: "Close overlay / palette" },
    ],
  },
  {
    heading: "Kanban (project page)",
    items: [
      { keys: ["space"], description: "Peek card without opening" },
      { keys: ["↵"], description: "Open card in slide-in pane" },
      { keys: ["j"], description: "Next card" },
      { keys: ["k"], description: "Previous card" },
      { keys: ["s"], description: "Change status" },
      { keys: ["⌘", "⌥", "1-4"], description: "Jump to column 1-4" },
      { keys: ["c"], description: "Change CLI agent (hover)" },
      { keys: ["r"], description: "Rename card (hover)" },
      { keys: ["d"], description: "Delete card (hover)" },
    ],
  },
];

export function KeyboardShortcutsOverlay() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
        return;
      }
      if (e.key !== "?") return;
      // Skip when user is typing somewhere editable.
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
      setOpen((prev) => !prev);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  // Programmatic opener for the command palette to call.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const opener = () => setOpen(true);
    window.addEventListener("selffork:show-shortcuts", opener);
    return () => window.removeEventListener("selffork:show-shortcuts", opener);
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 px-4 backdrop-blur-sm"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold tracking-tight">
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="max-h-[70vh] space-y-5 overflow-y-auto px-5 py-4 scrollbar-thin">
          {GROUPS.map((group) => (
            <section key={group.heading}>
              <h3 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                {group.heading}
              </h3>
              <ul className="space-y-1.5">
                {group.items.map((sc) => (
                  <li
                    key={sc.description}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="text-foreground">{sc.description}</span>
                    <span className="flex items-center gap-1">
                      {sc.keys.map((k, i) => (
                        <kbd
                          key={i}
                          className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                        >
                          {k}
                        </kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
