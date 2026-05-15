/**
 * Per-tier note list — Order 9.
 *
 * Plain markdown render of the note content; importance + intent +
 * tags surface as inline chips. Used by every TierSection except T3
 * (graph view, scope-out for M5+).
 */
"use client";

import { Streamdown } from "streamdown";

import type { NoteResponse } from "@/lib/api";

interface Props {
  notes: NoteResponse[];
}

export function NoteList({ notes }: Props) {
  if (notes.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No notes in this tier for the active project.
      </p>
    );
  }
  return (
    <ul className="space-y-3" data-testid="note-list">
      {notes.map((note) => (
        <li
          key={note.id}
          className="rounded border border-border/40 bg-background p-2"
          data-testid={`note-${note.id}`}
        >
          <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span className="font-mono">{note.kind}</span>
            {note.intent ? (
              <span>· {note.intent}</span>
            ) : null}
            {note.pinned ? <span>· pinned</span> : null}
            <span>· importance {note.importance.toFixed(2)}</span>
            {note.tag_keys.length > 0 ? (
              <span>· tags: {note.tag_keys.join(", ")}</span>
            ) : null}
          </div>
          <div className="prose prose-sm prose-invert max-w-none">
            <Streamdown>{note.content}</Streamdown>
          </div>
        </li>
      ))}
    </ul>
  );
}
