/**
 * Edit project metadata dialog — S7 (ADR-007 §4 S7).
 *
 * Wires ``PUT /api/projects/{slug}`` (server.py:1234, api.updateProject)
 * to a real shadcn modal. The slug is stable (PRD: slugs immutable);
 * only ``name`` / ``description`` / ``root_path`` are editable. An
 * empty ``root_path`` field clears the value (the backend honours the
 * sentinel-vs-empty distinction).
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
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  updateProject,
  type ProjectResponse,
} from "@/lib/api";

function errMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

export interface EditProjectDialogProps {
  project: ProjectResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: (project: ProjectResponse) => void;
}

export function EditProjectDialog({
  project,
  open,
  onOpenChange,
  onSaved,
}: EditProjectDialogProps) {
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const [rootPath, setRootPath] = useState(project?.root_path ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pull form values from the project whenever the dialog opens or the
  // project changes underfoot (e.g. a WS update lands while the operator
  // had Edit hovered). The dialog is transient — never the source of
  // truth.
  useEffect(() => {
    if (!open || project === null) return;
    setName(project.name);
    setDescription(project.description);
    setRootPath(project.root_path ?? "");
    setError(null);
    setSubmitting(false);
  }, [open, project]);

  if (project === null) return null;

  const trimmedName = name.trim();
  const canSubmit = !submitting && trimmedName.length > 0;

  async function handleSubmit() {
    if (!canSubmit || project === null) return;
    setSubmitting(true);
    setError(null);
    const payload: {
      name?: string;
      description?: string;
      root_path?: string;
    } = {};
    if (trimmedName !== project.name) payload.name = trimmedName;
    if (description !== project.description) payload.description = description;
    // root_path: send "" to clear, the path string to set, or omit when
    // the field matches the current value (no-op).
    const currentRoot = project.root_path ?? "";
    if (rootPath !== currentRoot) payload.root_path = rootPath;
    if (Object.keys(payload).length === 0) {
      // Nothing to persist; close cleanly.
      onOpenChange(false);
      setSubmitting(false);
      return;
    }
    try {
      const updated = await updateProject(project.slug, payload);
      onSaved?.(updated);
      onOpenChange(false);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLElement>) {
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
          <DialogTitle>Edit workspace</DialogTitle>
          <DialogDescription className="text-on-surface-variant">
            Slug stays stable ({project.slug}) — only the display fields
            update. Send an empty Root path to clear it.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-1">
          <div className="grid gap-1.5">
            <Label htmlFor="edit-project-name">Name</Label>
            <Input
              id="edit-project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={submitting}
              autoFocus
              maxLength={120}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="edit-project-desc">Description</Label>
            <Textarea
              id="edit-project-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={submitting}
              rows={4}
              placeholder="Short description for the operator's reference (optional)."
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="edit-project-root">Root path</Label>
            <Input
              id="edit-project-root"
              value={rootPath}
              onChange={(e) => setRootPath(e.target.value)}
              disabled={submitting}
              placeholder="/path/to/your/repo (optional)"
              spellCheck={false}
            />
            <p className="text-[11px] text-on-surface-variant">
              When set,{" "}
              <code className="font-mono bg-surface-container-low px-1 py-0.5 rounded">
                selffork run --project {project.slug}
              </code>{" "}
              cwd&apos;s into this path. Empty = scratch sandbox.
            </p>
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
          <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {submitting ? "Saving…" : "Save"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
