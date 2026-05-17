import { Edit2, Plus, StickyNote } from "lucide-react";

export interface ProjectNote {
  id: string;
  section: string;
  bullets: string[];
}

export interface ProjectNotesProps {
  notes: ProjectNote[];
  lastUpdate?: string; // "8m ago"
  onEdit?: () => void;
  onAddSection?: () => void;
}

export function ProjectNotes({
  notes,
  lastUpdate,
  onEdit,
  onAddSection,
}: ProjectNotesProps) {
  return (
    <section className="bg-surface rounded-xl shadow-sm border border-outline-variant/10 overflow-hidden">
      <header className="px-6 py-4 border-b border-outline-variant/20 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <StickyNote className="h-5 w-5 text-on-surface-variant" strokeWidth={1.75} />
          <h3 className="font-heading text-heading text-on-surface">
            Self Jr's notes
          </h3>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && (
            <span className="text-caption text-on-surface-variant tabular-nums">
              Last update: {lastUpdate}
            </span>
          )}
          <button
            type="button"
            onClick={onEdit}
            className="text-on-surface-variant hover:text-on-surface flex items-center gap-1 text-caption font-medium px-2 py-1 rounded transition-colors"
          >
            <Edit2 className="h-4 w-4" strokeWidth={1.75} />
            Edit
          </button>
          <button
            type="button"
            onClick={onAddSection}
            className="text-primary hover:bg-primary/5 flex items-center gap-1 text-caption font-medium px-2 py-1 rounded transition-colors"
          >
            <Plus className="h-4 w-4" strokeWidth={1.75} />
            Add section
          </button>
        </div>
      </header>
      <div className="px-6 py-6 space-y-6">
        {notes.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-caption text-on-surface-variant/70 italic">
              Self Jr hasn't written notes for this workspace yet.
            </p>
            <p className="text-caption text-on-surface-variant/50 mt-1">
              They'll appear here as decisions and learnings accumulate.
            </p>
          </div>
        ) : (
          notes.map((note) => (
            <div key={note.id}>
              <h4 className="text-body font-bold text-on-surface mb-2">
                # {note.section}
              </h4>
              <ul className="space-y-1">
                {note.bullets.map((b, i) => (
                  <li
                    key={i}
                    className="text-caption text-on-surface-variant pl-3 border-l-2 border-outline-variant/30"
                  >
                    {b}
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
