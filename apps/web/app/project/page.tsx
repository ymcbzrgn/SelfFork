/**
 * Project detail — header + provider usage strip + kanban board + sessions.
 *
 * Reads the slug from a URL search param (``?slug=<slug>``) so the
 * route is statically exportable.
 *
 * The kanban board reads ``GET /api/projects/<slug>/kanban`` every 5s
 * — keeps Yamaç-and-Jr's edits visible without WebSocket plumbing.
 * Adding cards / moving cards / marking done is fully wired to the
 * REST endpoints; no optimistic UI yet (refetch after each mutation).
 */
"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Edit2,
  Folder,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { Suspense, useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { RelativeAge } from "@/components/format";
import { AppShell } from "@/components/layout/app-shell";
import { ProviderUsageStrip } from "@/components/provider-usage-strip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type KanbanCardResponse,
  type KanbanResponse,
  type ProjectResponse,
  addKanbanCard,
  deleteKanbanCard,
  getKanban,
  getProject,
  moveKanbanCard,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const COLUMN_TONE: Record<string, string> = {
  backlog: "border-border bg-muted/40",
  in_progress: "border-info/30 bg-info/5",
  review: "border-warning/30 bg-warning/5",
  done: "border-success/30 bg-success/5",
};

const COLUMN_LABEL: Record<string, string> = {
  backlog: "Backlog",
  in_progress: "In progress",
  review: "Review",
  done: "Done",
};

export default function ProjectDetailPage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Project">
          <Skeleton className="h-32 w-full" />
        </AppShell>
      }
    >
      <ProjectDetail />
    </Suspense>
  );
}

function ProjectDetail() {
  const params = useSearchParams();
  const slug = params.get("slug");

  if (!slug) {
    return (
      <AppShell title="Project">
        <ErrorState
          title="Missing slug"
          detail="Open this page from /projects/ so the URL carries ?slug=..."
        />
      </AppShell>
    );
  }

  return (
    <AppShell title={`Project · ${slug}`}>
      <ProjectBody slug={slug} />
    </AppShell>
  );
}

function ProjectBody({ slug }: { slug: string }) {
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [board, setBoard] = useState<KanbanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, k] = await Promise.all([getProject(slug), getKanban(slug)]);
      setProject(p);
      setBoard(k);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [slug]);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), 5_000);
    return () => clearInterval(t);
  }, [refresh]);

  if (error && project === null) {
    return (
      <ErrorState
        title="Couldn't load project"
        detail={error}
      />
    );
  }
  if (project === null || board === null) {
    return <Skeleton className="h-64 w-full" />;
  }

  return (
    <div className="space-y-6">
      <ProjectHeader project={project} />
      <section className="space-y-3">
        <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Provider usage
        </h3>
        <ProviderUsageStrip />
      </section>
      <KanbanBoard slug={slug} board={board} onChanged={() => void refresh()} />
    </div>
  );
}

function ProjectHeader({ project }: { project: ProjectResponse }) {
  return (
    <div className="space-y-3">
      <Link
        href="/projects/"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
      >
        <ArrowLeft className="h-3 w-3" />
        All projects
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Folder className="h-5 w-5 text-muted-foreground" />
            {project.name}
          </h2>
          <p className="font-mono text-xs text-muted-foreground">
            slug: {project.slug}
            {project.root_path ? (
              <>
                {" "}· root: <span title={project.root_path}>{project.root_path}</span>
              </>
            ) : null}
          </p>
          {project.description ? (
            <p className="max-w-3xl text-sm text-muted-foreground">
              {project.description}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-1 text-[11px] text-muted-foreground">
          <span>
            updated <RelativeAge isoTs={project.updated_at} />
          </span>
          <span>
            created <RelativeAge isoTs={project.created_at} />
          </span>
        </div>
      </div>
    </div>
  );
}

function KanbanBoard({
  slug,
  board,
  onChanged,
}: {
  slug: string;
  board: KanbanResponse;
  onChanged: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Kanban</CardTitle>
        <p className="text-xs text-muted-foreground">
          Add a card to the backlog. Jr's tool calls (
          <code className="font-mono">kanban_card_done</code>,
          <code className="font-mono">kanban_card_move</code>) update
          this board live.
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {board.columns.map((col) => (
            <Column
              key={col}
              slug={slug}
              column={col}
              cards={board.cards_by_column[col] ?? []}
              onChanged={onChanged}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function Column({
  slug,
  column,
  cards,
  onChanged,
}: {
  slug: string;
  column: string;
  cards: KanbanCardResponse[];
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <div
      className={cn(
        "flex min-h-[12rem] flex-col rounded-lg border p-3",
        COLUMN_TONE[column] ?? "border-border bg-card",
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider">
          {COLUMN_LABEL[column] ?? column}
        </span>
        <Badge variant="outline" className="font-mono">
          {cards.length}
        </Badge>
      </div>

      <div className="flex-1 space-y-2">
        {cards.length === 0 ? (
          <p className="rounded-md border border-dashed border-border/60 p-3 text-center text-[11px] text-muted-foreground">
            Empty
          </p>
        ) : (
          cards.map((card) => (
            <KanbanCard
              key={card.id}
              slug={slug}
              card={card}
              onChanged={onChanged}
            />
          ))
        )}
      </div>

      {column === "backlog" ? (
        adding ? (
          <AddCardForm
            slug={slug}
            onCancel={() => setAdding(false)}
            onAdded={() => {
              setAdding(false);
              onChanged();
            }}
          />
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="mt-2 inline-flex items-center justify-center gap-1 rounded-md border border-dashed border-border/60 px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
          >
            <Plus className="h-3 w-3" />
            Add card
          </button>
        )
      ) : null}
    </div>
  );
}

function AddCardForm({
  slug,
  onCancel,
  onAdded,
}: {
  slug: string;
  onCancel: () => void;
  onAdded: () => void;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addKanbanCard(slug, { title: title.trim(), body: body.trim() });
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="mt-2 space-y-2 rounded-md border border-border bg-card p-2">
      <input
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Card title"
        className="w-full rounded border border-input bg-background px-2 py-1 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Optional details…"
        rows={2}
        className="w-full rounded border border-input bg-background px-2 py-1 text-[11px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
      />
      {error ? (
        <p className="text-[11px] text-destructive">{error}</p>
      ) : null}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="text-[11px] text-muted-foreground hover:text-foreground"
        >
          Cancel
        </button>
        <Button size="sm" type="submit" disabled={busy}>
          <Plus className="h-3 w-3" />
          {busy ? "Adding…" : "Add"}
        </Button>
      </div>
    </form>
  );
}

function KanbanCard({
  slug,
  card,
  onChanged,
}: {
  slug: string;
  card: KanbanCardResponse;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  const move = async (to: string) => {
    setBusy("move");
    try {
      await moveKanbanCard(slug, card.id, to);
      onChanged();
    } catch {
      // ignore — banner-level error UI not needed for one-shot moves
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    setBusy("delete");
    try {
      await deleteKanbanCard(slug, card.id);
      onChanged();
    } catch {
      // ignore
    } finally {
      setBusy(null);
    }
  };

  const next = _nextColumn(card.column);
  const prev = _prevColumn(card.column);

  return (
    <div className="group rounded-md border border-border bg-card p-2 text-xs shadow-sm transition-colors hover:border-foreground/30">
      <div className="flex items-start justify-between gap-2">
        <p className="flex-1 break-words font-medium leading-snug">
          {card.title}
        </p>
        <button
          type="button"
          onClick={remove}
          disabled={busy !== null}
          title="Delete card"
          className="opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive disabled:opacity-50"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
      {card.body ? (
        <p className="mt-1.5 line-clamp-2 text-[11px] text-muted-foreground">
          {card.body}
        </p>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
        <div className="flex items-center gap-1.5">
          {prev ? (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => move(prev)}
              title={`Move to ${prev}`}
              className="rounded p-0.5 hover:bg-accent disabled:opacity-50"
            >
              <ArrowLeft className="h-3 w-3" />
            </button>
          ) : null}
          {card.column === "done" ? (
            <Check className="h-3 w-3 text-success" />
          ) : null}
          {next ? (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => move(next)}
              title={`Move to ${next}`}
              className="rounded p-0.5 hover:bg-accent disabled:opacity-50"
            >
              <ArrowRight className="h-3 w-3" />
            </button>
          ) : null}
        </div>
        <span className="font-mono">
          updated <RelativeAge isoTs={card.updated_at} />
        </span>
      </div>
      {card.last_touched_by_session_id ? (
        <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground">
          last by {card.last_touched_by_session_id.slice(0, 12)}…
        </p>
      ) : null}
    </div>
  );
}

const _COLUMN_ORDER = ["backlog", "in_progress", "review", "done"];

function _nextColumn(col: string): string | null {
  const i = _COLUMN_ORDER.indexOf(col);
  if (i < 0 || i >= _COLUMN_ORDER.length - 1) return null;
  return _COLUMN_ORDER[i + 1];
}

function _prevColumn(col: string): string | null {
  const i = _COLUMN_ORDER.indexOf(col);
  if (i <= 0) return null;
  return _COLUMN_ORDER[i - 1];
}
