/**
 * Workspaces — Stitch-verbatim port. Bento-style 3-column grid of the
 * user's projects, sourced from real /api/projects. "+ New project"
 * opens a lightweight inline composer (Dialog) — no native window.prompt.
 *
 * Stitch design reference: screen 17897be313ab48619d77b11c4b35f37a.
 */
"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createProject,
  listProjects,
  type ProjectResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const GRADIENTS = [
  "bg-gradient-to-br from-primary/20 via-primary/5 to-surface-muted",
  "bg-gradient-to-br from-secondary-container/20 via-surface-muted to-surface",
  "bg-gradient-to-br from-tertiary-container/10 via-surface-muted to-white",
  "bg-gradient-to-br from-primary/15 via-white to-surface-muted",
  "bg-gradient-to-br from-on-secondary-container/10 via-surface-muted to-surface",
  "bg-gradient-to-br from-primary/10 via-surface-muted to-white",
];

function gradientFor(slug: string): string {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return GRADIENTS[h % GRADIENTS.length];
}

function statusOf(project: ProjectResponse): "ready" | "in progress" {
  const cc = project.card_counts ?? {};
  const wip = (cc.in_progress ?? 0) + (cc.review ?? 0);
  return wip > 0 ? "in progress" : "ready";
}

export default function WorkspacesPage() {
  const [projects, setProjects] = useState<ProjectResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const refresh = () => {
    listProjects()
      .then((data) => {
        setProjects(data);
        setError(null);
      })
      .catch((e: Error) => {
        setError(`Could not load workspaces: ${e.message}`);
        setProjects([]);
      });
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || creating) return;
    setCreating(true);
    try {
      await createProject({ name: newName.trim(), description: "" });
      setDialogOpen(false);
      setNewName("");
      refresh();
    } catch (e) {
      setError(`Could not create: ${(e as Error).message}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <AppShell title="Personal Space">
      <main className="flex-1 px-gutter-desktop py-vertical-gap max-w-7xl mx-auto w-full">
        <div className="flex items-center gap-6 mb-12">
          <h2 className="font-display text-display text-on-surface">
            Workspaces
          </h2>
          <button
            type="button"
            onClick={() => setDialogOpen(true)}
            className="bg-primary text-on-primary px-5 py-2.5 rounded-xl font-body text-body font-medium hover:opacity-90 transition-all flex items-center gap-2 active:scale-95"
          >
            <Plus className="h-[18px] w-[18px]" strokeWidth={2} />
            New project
          </button>
        </div>

        {error ? (
          <div
            role="alert"
            className="mb-8 rounded-xl bg-error-container/40 text-on-error-container px-card-padding py-4 font-body text-caption"
          >
            {error}
          </div>
        ) : null}

        {projects === null ? (
          <p className="font-body text-caption text-foreground-muted">
            Loading workspaces…
          </p>
        ) : projects.length === 0 ? (
          <div className="bg-surface rounded-[16px] shadow-[0_2px_8px_rgba(15,23,42,0.04)] p-12 flex flex-col items-center text-center">
            <p className="font-body text-body text-foreground-muted mb-6">
              Nothing here yet. Start something.
            </p>
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              className="bg-primary text-on-primary px-5 py-2.5 rounded-xl font-body text-body font-medium hover:opacity-90 transition-all flex items-center gap-2 active:scale-95"
            >
              <Plus className="h-[18px] w-[18px]" strokeWidth={2} />
              New project
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {projects.map((p) => {
              const status = statusOf(p);
              return (
                <Link
                  key={p.slug}
                  href={`/talk?workspace=${p.slug}`}
                  className="bg-surface rounded-[16px] shadow-[0_2px_8px_rgba(15,23,42,0.04)] hover:-translate-y-[2px] hover:shadow-[0_4px_12px_rgba(15,23,42,0.08)] transition-all duration-200 overflow-hidden flex flex-col"
                >
                  <div
                    className={cn(
                      "h-32 w-full relative overflow-hidden",
                      gradientFor(p.slug),
                    )}
                  />
                  <div className="p-card-padding">
                    <h3 className="font-heading text-heading mb-1 truncate">
                      {p.name}
                    </h3>
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "w-2 h-2 rounded-full",
                          status === "ready"
                            ? "bg-success"
                            : "bg-primary-container animate-pulse",
                        )}
                      />
                      <span className="font-caption text-caption text-foreground-muted">
                        {status}
                      </span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </main>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="bg-surface rounded-2xl">
          <DialogHeader>
            <DialogTitle className="font-heading text-heading text-on-surface">
              New workspace
            </DialogTitle>
            <DialogDescription className="font-body text-body text-foreground-muted">
              Give it a name. You can change everything later.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-2">
              <Label
                htmlFor="workspace-name"
                className="font-caption text-caption text-on-surface-variant"
              >
                Name
              </Label>
              <Input
                id="workspace-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Auth rewrite"
                disabled={creating}
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setDialogOpen(false)}
                disabled={creating}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!newName.trim() || creating}
                className="bg-primary text-on-primary hover:opacity-90"
              >
                {creating ? "Creating…" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
