/**
 * Add Kanban card dialog — workspace-scoped.
 *
 * Wires the existing POST /api/projects/{slug}/kanban/cards backend
 * (server.py:1285, api.addKanbanCard) to a real shadcn modal. The
 * caller owns the open state and provides the available columns from
 * the live KanbanResponse (no hardcoded column list — project_ui_stack
 * no-mock rule).
 */
"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ApiError,
  addKanbanCard,
  type KanbanCardResponse,
} from "@/lib/api";

function errMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

export interface AddKanbanCardDialogProps {
  slug: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Live column list from KanbanResponse — no hardcoded fallback. */
  columns: string[];
  /** Preselect a column (e.g. operator clicked "+ task" inside a specific column). */
  defaultColumn?: string;
  /** Fires after the backend confirms the card was created. */
  onAdded?: (card: KanbanCardResponse) => void;
}

export function AddKanbanCardDialog({
  slug,
  open,
  onOpenChange,
  columns,
  defaultColumn,
  onAdded,
}: AddKanbanCardDialogProps) {
  const fallbackColumn = defaultColumn ?? columns[0] ?? "Backlog";
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [column, setColumn] = useState(fallbackColumn);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      // Reset the form whenever the dialog is re-opened so a previous
      // partial entry doesn't leak across opens. The submission path
      // also resets after success.
      setTitle("");
      setBody("");
      setColumn(fallbackColumn);
      setError(null);
      setSubmitting(false);
    }
    // We intentionally only react to `open` flipping true — the
    // `fallbackColumn` derivation is stable across renders for a
    // given (defaultColumn, columns) tuple, and listing it as a dep
    // would re-reset mid-edit if the parent ever reflowed columns.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const titleTrimmed = title.trim();
  const canSubmit = !submitting && titleTrimmed.length > 0;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const card = await addKanbanCard(slug, {
        title: titleTrimmed,
        body: body.trim() || undefined,
        column,
      });
      onAdded?.(card);
      onOpenChange(false);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLElement>) {
    // Cmd/Ctrl+Enter submits — mirrors the talk/page send shortcut.
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void handleSubmit();
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (submitting) return;
        onOpenChange(next);
      }}
    >
      <DialogContent
        className="bg-surface text-on-surface border-outline-variant max-w-lg"
        onKeyDown={handleKeyDown}
      >
        <DialogHeader>
          <DialogTitle>Add a Kanban task</DialogTitle>
          <DialogDescription className="text-on-surface-variant">
            Lands in the chosen column. Self Jr can pick it up on the
            next autopilot tick.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-1">
          <div className="grid gap-1.5">
            <Label htmlFor="kanban-add-title">Title</Label>
            <Input
              id="kanban-add-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Build the login screen"
              disabled={submitting}
              autoFocus
              maxLength={200}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="kanban-add-body">Description (optional)</Label>
            <textarea
              id="kanban-add-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Acceptance criteria, links, notes…"
              disabled={submitting}
              rows={4}
              className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 resize-y"
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="kanban-add-column">Column</Label>
            <Select
              value={column}
              onValueChange={setColumn}
              disabled={submitting}
            >
              <SelectTrigger id="kanban-add-column">
                <SelectValue placeholder="Pick a column" />
              </SelectTrigger>
              <SelectContent>
                {columns.map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {error && (
            <p className="text-caption text-error" role="alert">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
          >
            {submitting ? "Adding…" : "Add task"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
