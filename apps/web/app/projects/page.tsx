/**
 * Projects index page — grid of project cards with kanban counts.
 */
"use client";

import Link from "next/link";
import { ArrowUpRight, FolderPlus, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { RelativeAge } from "@/components/format";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type ProjectResponse, listProjects } from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "ok"; data: ProjectResponse[] }
  | { status: "error"; error: string };

export default function ProjectsPage() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await listProjects();
        if (!cancelled) setState({ status: "ok", data });
      } catch (e) {
        if (!cancelled) {
          setState({
            status: "error",
            error: e instanceof Error ? e.message : String(e),
          });
        }
      }
    };
    void poll();
    const t = setInterval(() => void poll(), 5_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return (
    <AppShell title="Projects">
      <div className="space-y-6">
        <div className="flex items-end justify-between">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">Projects</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Each project owns a kanban board, a workspace, and the
              sessions it spawns.
            </p>
          </div>
          <Link
            href="/projects/new/"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            New project
          </Link>
        </div>

        {state.status === "loading" ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        ) : state.status === "error" ? (
          <ErrorState
            title="Couldn't load projects"
            detail={state.error ?? undefined}
          />
        ) : state.data.length === 0 ? (
          <EmptyState
            title="No projects yet"
            hint={
              <>
                Click <span className="font-medium">New project</span>{" "}
                above, or run{" "}
                <code className="font-mono">
                  selffork project create &lt;name&gt;
                </code>{" "}
                in a terminal.
              </>
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {state.data.map((p) => (
              <ProjectCard key={p.slug} project={p} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function ProjectCard({ project }: { project: ProjectResponse }) {
  const totalCards = Object.values(project.card_counts).reduce(
    (a, b) => a + b,
    0,
  );
  return (
    <Link
      href={`/project/?slug=${project.slug}`}
      className="group block"
    >
      <Card className="h-full p-5 transition-colors hover:border-foreground/40 hover:bg-accent/30">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-base font-semibold">
              {project.name}
            </h3>
            <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">
              {project.slug}
            </p>
          </div>
          <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </div>
        {project.description ? (
          <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">
            {project.description}
          </p>
        ) : null}
        <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[11px]">
          {Object.entries(project.card_counts).map(([col, n]) => (
            <span
              key={col}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary/40 px-2 py-0.5 font-mono tabular-nums"
              title={`${n} card${n === 1 ? "" : "s"} in ${col}`}
            >
              <span className="text-muted-foreground">{col}</span>
              <span>{n}</span>
            </span>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
          <span>{totalCards} total cards</span>
          <span>
            updated <RelativeAge isoTs={project.updated_at} />
          </span>
        </div>
      </Card>
    </Link>
  );
}
