/**
 * Start a new ``selffork run`` from the dashboard.
 *
 * The form is intentionally thin: PRD path + optional config path. Both
 * are server-side filesystem paths — we don't do file uploads (the
 * backend would need to write them somewhere, which is a whole extra
 * concern for MVP). The user has the PRD on disk; they paste the path.
 */
"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  FileText,
  Folder,
  Play,
  Settings,
  Terminal,
} from "lucide-react";
import { useEffect, useState } from "react";

import { ErrorState } from "@/components/error-state";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ProjectResponse,
  listProjects,
  startRun,
} from "@/lib/api";

interface SuccessState {
  pid: number | null;
  detail: string | null;
}

export default function RunPage() {
  const [prdPath, setPrdPath] = useState("");
  const [configPath, setConfigPath] = useState("");
  const [projectSlug, setProjectSlug] = useState("");
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<SuccessState | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await listProjects();
        if (!cancelled) setProjects(data);
      } catch {
        // sidebar already shows the error; here we just silently fall
        // back to the no-project option.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!prdPath.trim()) {
      setError("PRD path is required.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await startRun(
        prdPath.trim(),
        configPath.trim() ? configPath.trim() : undefined,
        projectSlug ? projectSlug : undefined,
      );
      if (res.status === "started") {
        setSuccess({ pid: res.pid, detail: res.detail });
      } else {
        setError(res.detail ?? res.status);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell title="New run">
      <div className="mx-auto max-w-2xl space-y-6">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          <ArrowLeft className="h-3 w-3" />
          All sessions
        </Link>

        <header className="space-y-1">
          <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
            <Terminal className="h-5 w-5" />
            Start a session
          </h2>
          <p className="text-sm text-muted-foreground">
            Spawn <code className="font-mono">selffork run &lt;prd&gt;</code>{" "}
            on the host. The subprocess writes its own audit log; the
            dashboard refreshes to show it.
          </p>
        </header>

        <Card>
          <form onSubmit={submit}>
            <CardHeader>
              <CardTitle className="text-base">Inputs</CardTitle>
              <p className="text-xs text-muted-foreground">
                Both paths must already exist on disk. Tildes (
                <code className="font-mono">~</code>) are expanded by the
                backend.
              </p>
            </CardHeader>
            <CardContent className="space-y-5">
              <Field
                label="Project"
                hint={
                  projects.length === 0
                    ? "No projects yet — runs without a project go to the global audit log."
                    : "Pick a project so Jr's tool calls update its kanban. Leave blank for an orphan run."
                }
                icon={Folder}
              >
                <select
                  value={projectSlug}
                  onChange={(e) => setProjectSlug(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/40"
                >
                  <option value="">— no project (orphan) —</option>
                  {projects.map((p) => (
                    <option key={p.slug} value={p.slug}>
                      {p.name} ({p.slug})
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                label="PRD path"
                hint="Absolute or tilde-prefixed (~/projects/foo/prd.md)."
                icon={FileText}
                required
              >
                <input
                  value={prdPath}
                  onChange={(e) => setPrdPath(e.target.value)}
                  required
                  placeholder="~/projects/calc/prd.md"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm transition-colors focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/40"
                />
              </Field>
              <Field
                label="Config path"
                hint={
                  <>
                    Optional. Defaults to{" "}
                    <code className="font-mono">./selffork.yaml</code> in
                    the host's cwd.
                  </>
                }
                icon={Settings}
              >
                <input
                  value={configPath}
                  onChange={(e) => setConfigPath(e.target.value)}
                  placeholder="/path/to/selffork.yaml"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm transition-colors focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/40"
                />
              </Field>
              {error ? (
                <ErrorState title="Couldn't start" detail={error} />
              ) : null}
              {success ? <SuccessPanel state={success} /> : null}
            </CardContent>
            <div className="flex items-center justify-between gap-3 border-t border-border bg-secondary/30 px-6 py-3">
              <p className="text-[11px] text-muted-foreground">
                <AlertTriangle className="mr-1 inline h-3 w-3 text-warning" />
                The dashboard never uploads files. Both paths must
                resolve on the host filesystem.
              </p>
              <Button type="submit" disabled={submitting}>
                <Play className="h-3.5 w-3.5" />
                {submitting ? "Starting…" : "Start run"}
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
  icon: Icon,
  required,
  children,
}: {
  label: string;
  hint?: React.ReactNode;
  icon: typeof FileText;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="flex items-center gap-1.5 text-foreground">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
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

function SuccessPanel({ state }: { state: SuccessState }) {
  return (
    <div className="rounded-lg border border-success/40 bg-success/5 p-4 text-sm">
      <p className="flex items-center gap-2 font-medium text-success">
        <CheckCircle2 className="h-4 w-4" />
        Spawn requested
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        pid <code className="font-mono">{state.pid ?? "?"}</code>
        {state.detail ? ` · ${state.detail}` : ""}
      </p>
      <p className="mt-3">
        <Link
          href="/"
          className="text-xs font-medium text-foreground underline-offset-4 hover:underline"
        >
          Open dashboard to watch the new session →
        </Link>
      </p>
    </div>
  );
}
