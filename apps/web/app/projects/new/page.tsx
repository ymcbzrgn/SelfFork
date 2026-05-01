/**
 * Create-project form.
 *
 * Posts to ``POST /api/projects`` and on success navigates to the
 * detail page (``/project/?slug=<slug>``). When the slug already
 * exists or the name is invalid, the backend returns 400 + detail
 * which we surface verbatim.
 */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, FolderPlus } from "lucide-react";
import { useState } from "react";

import { ErrorState } from "@/components/error-state";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createProject } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    setSubmitting(true);
    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim(),
        root_path: rootPath.trim() ? rootPath.trim() : null,
      });
      router.push(`/project/?slug=${project.slug}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  };

  return (
    <AppShell title="New project">
      <div className="mx-auto max-w-2xl space-y-6">
        <Link
          href="/projects/"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          <ArrowLeft className="h-3 w-3" />
          All projects
        </Link>

        <header className="space-y-1">
          <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
            <FolderPlus className="h-5 w-5" />
            Create a project
          </h2>
          <p className="text-sm text-muted-foreground">
            A project owns a kanban board, sessions and (optionally) an
            existing repo on disk to operate on.
          </p>
        </header>

        <Card>
          <form onSubmit={submit}>
            <CardHeader>
              <CardTitle className="text-base">Inputs</CardTitle>
              <p className="text-xs text-muted-foreground">
                The slug is generated from the name; spaces and Turkish
                characters get normalised.
              </p>
            </CardHeader>
            <CardContent className="space-y-5">
              <Field label="Name" required>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  placeholder="Calculator MVP"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/40"
                />
              </Field>
              <Field
                label="Description"
                hint="Free-text. Surfaces on the dashboard."
              >
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What this project is for…"
                  rows={3}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/40"
                />
              </Field>
              <Field
                label="Bind to existing repo (optional)"
                hint={
                  <>
                    Absolute or tilde-prefixed path. When set,{" "}
                    <code className="font-mono">selffork run --project</code>{" "}
                    cwd's into this directory. Leave blank to use a fresh
                    sandbox.
                  </>
                }
              >
                <input
                  value={rootPath}
                  onChange={(e) => setRootPath(e.target.value)}
                  placeholder="~/projects/calc"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/40"
                />
              </Field>
              {error ? (
                <ErrorState title="Couldn't create" detail={error} />
              ) : null}
            </CardContent>
            <div className="flex items-center justify-end gap-3 border-t border-border bg-secondary/30 px-6 py-3">
              <Button type="submit" disabled={submitting}>
                <FolderPlus className="h-3.5 w-3.5" />
                {submitting ? "Creating…" : "Create project"}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </AppShell>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: React.ReactNode;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="flex items-center gap-1 text-foreground">
        {label}
        {required ? (
          <span aria-hidden className="text-destructive">
            *
          </span>
        ) : null}
      </span>
      {children}
      {hint ? (
        <span className="block text-[11px] text-muted-foreground">{hint}</span>
      ) : null}
    </label>
  );
}
