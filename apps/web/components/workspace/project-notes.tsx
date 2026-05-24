/**
 * Project notes — S7 (ADR-007 §4 S7).
 *
 * 2-pane workspace surface: sidebar with note titles (intent field)
 * + main editor (@uiw/react-md-editor) bound to ``content``. All
 * persistence is parent-owned via the handler props — this component
 * is stateless about the wire shape.
 *
 * Operator pick (AskUserQuestion 2026-05-24): ``@uiw/react-md-editor``
 * for the markdown surface — mature, MIT, ~55 KB gzip, split-pane
 * preview, shadcn-friendly token surface.
 *
 * Persistence model: each Note row is bi-temporally superseded on
 * edit (see ``PATCH /api/projects/<slug>/mind/notes/<id>`` in
 * ``mind_router.py``). The parent debounces save calls to avoid one
 * superseded row per keystroke; here we just emit change events and
 * let the parent throttle.
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Edit2, Plus, StickyNote, Trash2 } from "lucide-react";

import "@uiw/react-md-editor/markdown-editor.css";
import "@uiw/react-markdown-preview/markdown.css";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import type { NoteResponse } from "@/lib/api";

// MDEditor pulls in CodeMirror + remark plumbing — bundle weight is
// real and SSR rendering isn't useful (no operator on the server). Use
// ``next/dynamic`` so the bundle splits and the editor doesn't ship
// on the workspace's other tabs.
const MDEditor = dynamic(
  async () => (await import("@uiw/react-md-editor")).default,
  {
    ssr: false,
    loading: () => (
      <div className="flex-1 flex items-center justify-center text-caption text-on-surface-variant italic">
        Loading editor…
      </div>
    ),
  },
);

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`;
  return `${Math.floor(ms / 86_400_000)}d ago`;
}

export interface ProjectNotesProps {
  notes: NoteResponse[];
  loading?: boolean;
  saving?: boolean;
  /** Pre-selected note id — wins over the "first note" default. */
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  onAdd?: () => void;
  onTitleChange?: (id: string, intent: string) => void;
  onContentChange?: (id: string, content: string) => void;
  onDelete?: (id: string) => void;
}

export function ProjectNotes({
  notes,
  loading,
  saving,
  selectedId,
  onSelect,
  onAdd,
  onTitleChange,
  onContentChange,
  onDelete,
}: ProjectNotesProps) {
  // Track local selection when the parent doesn't drive it — the
  // sidebar still needs to highlight the active row even when the
  // parent only cares about list mutations.
  const [internalId, setInternalId] = useState<string | null>(
    selectedId ?? notes[0]?.id ?? null,
  );
  const effectiveId = selectedId ?? internalId;

  useEffect(() => {
    if (selectedId !== undefined) return;
    // Auto-select first note when notes list changes; clear when
    // emptied. Avoid replacing a still-valid selection.
    if (
      notes.length > 0 &&
      (internalId === null || !notes.some((n) => n.id === internalId))
    ) {
      setInternalId(notes[0].id);
    } else if (notes.length === 0 && internalId !== null) {
      setInternalId(null);
    }
  }, [notes, internalId, selectedId]);

  const selected = useMemo(
    () => notes.find((n) => n.id === effectiveId) ?? null,
    [notes, effectiveId],
  );

  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  function selectNote(id: string | null) {
    if (selectedId === undefined) setInternalId(id);
    onSelect?.(id);
  }

  return (
    <section className="bg-surface rounded-xl shadow-sm border border-outline-variant/10 overflow-hidden grid grid-cols-1 md:grid-cols-12 min-h-[520px]">
      <aside className="md:col-span-3 border-r border-outline-variant/30 flex flex-col">
        <header className="px-4 py-3 border-b border-outline-variant/20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <StickyNote
              className="h-4 w-4 text-on-surface-variant"
              strokeWidth={1.75}
            />
            <h3 className="font-semibold text-caption text-on-surface">
              Notes
            </h3>
            <span className="text-[10px] text-on-surface-variant tabular-nums">
              {notes.length}
            </span>
          </div>
          <button
            type="button"
            onClick={onAdd}
            disabled={!onAdd}
            className="p-1 hover:bg-surface-container rounded text-on-surface-variant hover:text-on-surface transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="New note"
            title="New note"
          >
            <Plus className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </header>
        <ul className="flex-1 overflow-y-auto" aria-label="Notes">
          {loading && (
            <li className="px-4 py-3 text-caption text-on-surface-variant italic">
              Loading…
            </li>
          )}
          {!loading && notes.length === 0 && (
            <li className="px-4 py-3 text-caption text-on-surface-variant/70 italic">
              No notes yet.
            </li>
          )}
          {notes.map((n) => {
            const isActive = n.id === effectiveId;
            return (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => selectNote(n.id)}
                  className={
                    isActive
                      ? "w-full text-left px-4 py-2 border-l-2 border-primary bg-primary/5"
                      : "w-full text-left px-4 py-2 border-l-2 border-transparent hover:bg-surface-container-low"
                  }
                >
                  <div className="text-caption font-semibold text-on-surface line-clamp-1">
                    {n.intent || "(untitled)"}
                  </div>
                  <div className="text-[10px] text-on-surface-variant tabular-nums mt-0.5">
                    {relativeTime(n.valid_from)}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <div className="md:col-span-9 flex flex-col">
        {selected ? (
          <>
            <header className="px-4 py-3 border-b border-outline-variant/20 flex items-center gap-2">
              <Edit2
                className="h-3.5 w-3.5 text-on-surface-variant flex-shrink-0"
                strokeWidth={1.75}
              />
              <Input
                value={selected.intent}
                onChange={(e) =>
                  onTitleChange?.(selected.id, e.target.value)
                }
                placeholder="Note title"
                className="flex-1 border-none focus-visible:ring-0 focus-visible:ring-offset-0 px-0 text-body font-semibold shadow-none bg-transparent h-auto py-0"
                aria-label="Note title"
                maxLength={200}
              />
              {saving && (
                <span className="text-[10px] text-on-surface-variant italic flex-shrink-0">
                  Saving…
                </span>
              )}
              <button
                type="button"
                onClick={() => setDeleteConfirmOpen(true)}
                disabled={!onDelete}
                className="p-1 hover:bg-error-container/30 rounded text-on-surface-variant hover:text-error transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                aria-label="Delete note"
                title="Delete note"
              >
                <Trash2 className="h-4 w-4" strokeWidth={1.75} />
              </button>
            </header>
            <div
              className="flex-1 p-4 overflow-hidden"
              data-color-mode="light"
            >
              <MDEditor
                value={selected.content}
                onChange={(val) =>
                  onContentChange?.(selected.id, val ?? "")
                }
                preview="edit"
                height={440}
                visibleDragbar={false}
                textareaProps={{
                  placeholder: "Write the decision, learning, or context…",
                  spellCheck: true,
                }}
              />
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center p-8 text-center">
            <p className="text-caption text-on-surface-variant/60 italic max-w-sm">
              Self Jr hasn&apos;t written notes for this workspace yet.
              <br />
              Click + to add one — operator decisions land in Mind T2
              Episodic with a full bi-temporal audit trail.
            </p>
          </div>
        )}
      </div>

      <AlertDialog
        open={deleteConfirmOpen}
        onOpenChange={setDeleteConfirmOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this note?</AlertDialogTitle>
            <AlertDialogDescription>
              Removes it from the workspace listing. The note is
              bi-temporally superseded (kept for audit + M7 dataset);
              you won&apos;t see it here again unless you query the
              underlying Mind store directly.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                if (selected !== null && onDelete) onDelete(selected.id);
                setDeleteConfirmOpen(false);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
