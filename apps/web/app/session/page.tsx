/**
 * Session detail — header + plan + workspace + filtered live audit stream.
 *
 * Reads the session id from a URL search param (``?id=<ulid>``) so the
 * route is fully static-exportable: Next.js dynamic ``[id]`` segments
 * + ``"use client"`` are mutually exclusive in static export, and the
 * dashboard runtime mints session IDs we can't enumerate at build time.
 *
 * Per project_ui_stack.md every section reads from a real backend
 * endpoint. Sections backed by no data are rendered as EmptyState, NOT
 * hidden — the user must see what's there vs what's missing.
 */
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Activity,
  ArrowDown,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Copy,
  FileCode,
  FolderTree,
  Loader2,
  Pause,
  Play,
  X,
} from "lucide-react";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { AppShell } from "@/components/layout/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type AuditEvent,
  type PlanSnapshot,
  type WorkspaceEntry,
  ApiError,
  getSessionEvents,
  getSessionPlan,
  getSessionWorkspace,
  openSessionStream,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export default function SessionDetailPage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Session">
          <Skeleton className="h-24 w-full" />
        </AppShell>
      }
    >
      <SessionDetail />
    </Suspense>
  );
}

function SessionDetail() {
  const params = useSearchParams();
  const id = params.get("id");

  if (!id) {
    return (
      <AppShell title="Session">
        <ErrorState
          title="Missing session id"
          detail="Open this page from the dashboard so the URL carries ?id=..."
        />
      </AppShell>
    );
  }

  return (
    <AppShell title={`Session ${id.slice(0, 8)}…`}>
      <div className="space-y-6">
        <SessionHeader sessionId={id} />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <PlanCard sessionId={id} />
          <WorkspaceCard sessionId={id} />
        </div>
        <AuditStreamCard sessionId={id} />
      </div>
    </AppShell>
  );
}

// ── Header ────────────────────────────────────────────────────────────────────

function SessionHeader({ sessionId }: { sessionId: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.clipboard) return;
    await navigator.clipboard.writeText(sessionId);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }, [sessionId]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            <ArrowLeft className="h-3 w-3" />
            All sessions
          </Link>
          <h2 className="mt-2 break-all font-mono text-lg font-semibold tracking-tight">
            {sessionId}
          </h2>
        </div>
        <Button variant="outline" size="sm" onClick={copy}>
          <Copy className="h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy id"}
        </Button>
      </div>
    </div>
  );
}

// ── Plan ──────────────────────────────────────────────────────────────────────

function PlanCard({ sessionId }: { sessionId: string }) {
  const [state, setState] = useState<{
    status: "loading" | "ok" | "missing" | "error";
    data: PlanSnapshot | null;
    detail: string | null;
  }>({ status: "loading", data: null, detail: null });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getSessionPlan(sessionId);
        if (!cancelled) setState({ status: "ok", data, detail: null });
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setState({ status: "missing", data: null, detail: e.message });
        } else {
          setState({
            status: "error",
            data: null,
            detail: e instanceof Error ? e.message : String(e),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileCode className="h-4 w-4 text-muted-foreground" />
          Plan
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Snapshot of <code className="font-mono">.selffork/plan.json</code>{" "}
          inside the session's workspace.
        </p>
      </CardHeader>
      <CardContent>
        {state.status === "loading" ? (
          <Skeleton className="h-24 w-full" />
        ) : state.status === "missing" ? (
          <EmptyState
            title="No plan-as-state file"
            hint={
              "Plans are produced by the CLI agent during the round loop. " +
              "Backend currently exposes plan.json only for paused sessions."
            }
          />
        ) : state.status === "error" ? (
          <ErrorState
            title="Couldn't load plan"
            detail={state.detail ?? undefined}
          />
        ) : (
          <PlanContent plan={state.data!} />
        )}
      </CardContent>
    </Card>
  );
}

function PlanContent({ plan }: { plan: PlanSnapshot }) {
  return (
    <div className="space-y-3 text-sm">
      <p className="text-foreground">
        {plan.summary || (
          <em className="text-muted-foreground">no summary recorded</em>
        )}
      </p>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
        sub-tasks · {plan.sub_tasks.length}
      </div>
      {plan.sub_tasks.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No sub-tasks recorded yet.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {plan.sub_tasks.map((t, i) => (
            <PlanTaskRow key={i} task={t} />
          ))}
        </ul>
      )}
    </div>
  );
}

function PlanTaskRow({ task }: { task: Record<string, unknown> }) {
  const title = String(task.title ?? task.name ?? task.id ?? "(untitled)");
  const status = typeof task.status === "string" ? task.status : null;
  const tone =
    status === "done" || status === "completed"
      ? "success"
      : status === "failed"
        ? "danger"
        : status === "in_progress" || status === "running"
          ? "info"
          : "muted";
  return (
    <li className="flex items-center justify-between gap-3 rounded-md border border-border bg-secondary/30 px-3 py-2">
      <span className="truncate text-xs text-foreground">{title}</span>
      {status ? (
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-[10px] font-medium",
            tone === "success" && "border-success/40 bg-success/10 text-success",
            tone === "danger" &&
              "border-destructive/40 bg-destructive/10 text-destructive",
            tone === "info" && "border-info/40 bg-info/10 text-info",
            tone === "muted" &&
              "border-border bg-muted text-muted-foreground",
          )}
        >
          {status}
        </span>
      ) : null}
    </li>
  );
}

// ── Workspace ─────────────────────────────────────────────────────────────────

function WorkspaceCard({ sessionId }: { sessionId: string }) {
  const [state, setState] = useState<{
    status: "loading" | "ok" | "missing" | "error";
    data: WorkspaceEntry[] | null;
    detail: string | null;
  }>({ status: "loading", data: null, detail: null });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getSessionWorkspace(sessionId);
        if (!cancelled) setState({ status: "ok", data, detail: null });
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setState({ status: "missing", data: null, detail: e.message });
        } else {
          setState({
            status: "error",
            data: null,
            detail: e instanceof Error ? e.message : String(e),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <FolderTree className="h-4 w-4 text-muted-foreground" />
            Workspace
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Files written under the session's sandbox directory.
          </p>
        </div>
        {state.status === "ok" ? (
          <WorkspaceSummary entries={state.data ?? []} />
        ) : null}
      </CardHeader>
      <CardContent>
        {state.status === "loading" ? (
          <Skeleton className="h-24 w-full" />
        ) : state.status === "missing" ? (
          <EmptyState
            title="No workspace tree"
            hint="Backend currently exposes the workspace only for paused sessions."
          />
        ) : state.status === "error" ? (
          <ErrorState
            title="Couldn't load workspace"
            detail={state.detail ?? undefined}
          />
        ) : (state.data ?? []).length === 0 ? (
          <EmptyState title="Workspace is empty" />
        ) : (
          <WorkspaceTree entries={state.data!} />
        )}
      </CardContent>
    </Card>
  );
}

function WorkspaceSummary({ entries }: { entries: WorkspaceEntry[] }) {
  const files = entries.filter((e) => e.kind === "file").length;
  const totalBytes = entries
    .filter((e) => e.kind === "file")
    .reduce((acc, e) => acc + (e.size_bytes ?? 0), 0);
  return (
    <div className="flex shrink-0 flex-col items-end text-[11px] text-muted-foreground">
      <span className="font-mono tabular-nums">
        {files} file{files === 1 ? "" : "s"}
      </span>
      <span className="font-mono tabular-nums">{formatBytes(totalBytes)}</span>
    </div>
  );
}

function WorkspaceTree({ entries }: { entries: WorkspaceEntry[] }) {
  // Each entry's path is relative; the depth is the slash count. We render
  // each row indented by depth so the tree shape matches the filesystem.
  return (
    <ul className="max-h-72 space-y-0.5 overflow-auto font-mono text-xs scrollbar-thin">
      {entries.map((entry) => {
        const depth = entry.path.split("/").length - 1;
        const name = entry.path.split("/").pop() ?? entry.path;
        return (
          <li
            key={entry.path}
            className={cn(
              "flex items-center justify-between gap-2 rounded px-1 py-1 transition-colors hover:bg-secondary/40",
            )}
            style={{ paddingLeft: `${0.25 + depth * 0.85}rem` }}
          >
            <span className="flex min-w-0 items-center gap-1.5 truncate">
              <span aria-hidden className="text-muted-foreground">
                {entry.kind === "dir" ? "▸" : "·"}
              </span>
              <span
                className={cn(
                  "truncate",
                  entry.kind === "dir" && "text-foreground",
                )}
              >
                {name}
              </span>
            </span>
            {entry.kind === "file" ? (
              <span className="text-[10px] text-muted-foreground">
                {formatBytes(entry.size_bytes ?? 0)}
              </span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Audit stream ──────────────────────────────────────────────────────────────

interface StreamState {
  status: "connecting" | "streaming" | "closed" | "error";
  detail: string | null;
}

const CATEGORY_TONE: Record<string, string> = {
  "session.state": "border-info/40 bg-info/10 text-info",
  "runtime.start": "border-info/40 bg-info/10 text-info",
  "runtime.spawn": "border-info/40 bg-info/10 text-info",
  "runtime.ready": "border-success/40 bg-success/10 text-success",
  "runtime.stop": "border-border bg-muted text-muted-foreground",
  "runtime.stopped": "border-border bg-muted text-muted-foreground",
  "sandbox.spawn": "border-border bg-muted text-muted-foreground",
  "sandbox.exec": "border-info/40 bg-info/10 text-info",
  "sandbox.teardown": "border-border bg-muted text-muted-foreground",
  "agent.invoke": "border-info/40 bg-info/10 text-info",
  "agent.output": "border-success/40 bg-success/10 text-success",
  "agent.done": "border-success/40 bg-success/10 text-success",
  "agent.rate_limited": "border-warning/40 bg-warning/10 text-warning",
  "agent.auth_required":
    "border-destructive/40 bg-destructive/10 text-destructive",
  "agent.spawn_request": "border-info/40 bg-info/10 text-info",
  "agent.spawn_complete": "border-success/40 bg-success/10 text-success",
  "selffork_jr.reply": "border-info/40 bg-info/10 text-info",
  "plan.save": "border-border bg-muted text-muted-foreground",
  "plan.load": "border-border bg-muted text-muted-foreground",
  "plan.update": "border-border bg-muted text-muted-foreground",
  error: "border-destructive/40 bg-destructive/10 text-destructive",
};

function AuditStreamCard({ sessionId }: { sessionId: string }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [stream, setStream] = useState<StreamState>({
    status: "connecting",
    detail: null,
  });
  const [filter, setFilter] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);
  const scrollerRef = useRef<HTMLOListElement | null>(null);

  const connect = useCallback(() => {
    setStream({ status: "connecting", detail: null });
    setEvents([]);
    let ws: WebSocket;
    try {
      ws = openSessionStream(sessionId);
    } catch (e) {
      setStream({
        status: "error",
        detail: e instanceof Error ? e.message : String(e),
      });
      return;
    }
    wsRef.current = ws;
    ws.onopen = () => setStream({ status: "streaming", detail: null });
    ws.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data) as AuditEvent;
        setEvents((prev) => [...prev, evt]);
      } catch {
        // ignore malformed
      }
    };
    ws.onclose = (ev) => {
      setStream({
        status: "closed",
        detail: ev.reason || `code=${ev.code}`,
      });
    };
  }, [sessionId]);

  useEffect(() => {
    void (async () => {
      try {
        const initial = await getSessionEvents(sessionId);
        setEvents(initial);
      } catch {
        // 404 fine; WebSocket will surface events when they appear.
      }
    })();
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [sessionId, connect]);

  // Auto-scroll to bottom on new events when toggle is on.
  useEffect(() => {
    if (!autoScroll) return;
    const el = scrollerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [events, autoScroll]);

  const categories = useMemo(() => {
    const set = new Set<string>();
    for (const e of events) set.add(e.category);
    return Array.from(set).sort();
  }, [events]);

  const visible = useMemo(
    () => (filter ? events.filter((e) => e.category === filter) : events),
    [events, filter],
  );

  // Find session terminal state for the header.
  const terminalState = useMemo(() => {
    let last: string | null = null;
    for (const e of events) {
      if (e.category === "session.state") {
        const to = e.payload?.["to"];
        if (typeof to === "string") last = to;
      }
    }
    return last;
  }, [events]);

  const scrollToBottom = useCallback(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    setAutoScroll(true);
  }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4 text-muted-foreground" />
            Audit stream
            {terminalState ? <StatusBadge state={terminalState} /> : null}
          </CardTitle>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            <code className="font-mono">
              ~/.selffork/audit/{sessionId}.jsonl
            </code>{" "}
            · live via WebSocket
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <StreamBadge state={stream} />
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoScroll((s) => !s)}
            title={autoScroll ? "Pause auto-scroll" : "Resume auto-scroll"}
          >
            {autoScroll ? (
              <Pause className="h-3.5 w-3.5" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {autoScroll ? "Auto-scroll" : "Paused"}
          </Button>
          {!autoScroll ? (
            <Button variant="outline" size="sm" onClick={scrollToBottom}>
              <ArrowDown className="h-3.5 w-3.5" />
              Latest
            </Button>
          ) : null}
          {(stream.status === "closed" || stream.status === "error") && (
            <Button size="sm" variant="outline" onClick={connect}>
              Reconnect
            </Button>
          )}
        </div>
      </CardHeader>

      {events.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5 border-y border-border bg-secondary/30 px-6 py-2">
          <span className="mr-1 text-[10px] uppercase tracking-wider text-muted-foreground">
            filter
          </span>
          <FilterPill
            label="all"
            count={events.length}
            active={filter === null}
            onClick={() => setFilter(null)}
          />
          {categories.map((c) => (
            <FilterPill
              key={c}
              label={c}
              count={events.filter((e) => e.category === c).length}
              active={filter === c}
              onClick={() => setFilter(filter === c ? null : c)}
            />
          ))}
          {filter ? (
            <button
              type="button"
              onClick={() => setFilter(null)}
              className="ml-auto inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" />
              clear filter
            </button>
          ) : null}
        </div>
      ) : null}

      <CardContent className="pt-0">
        {events.length === 0 ? (
          <div className="py-6">
            <EmptyState
              title="No events yet"
              hint={
                stream.detail
                  ? `(stream ${stream.status}: ${stream.detail})`
                  : "Waiting for the first audit event…"
              }
            />
          </div>
        ) : (
          <>
            <ol
              ref={scrollerRef}
              className="max-h-[60vh] space-y-1 overflow-y-auto py-4 font-mono text-xs scrollbar-thin"
            >
              {visible.map((evt, i) => (
                <AuditEventRow key={`${evt.ts}-${i}`} event={evt} />
              ))}
            </ol>
            <div className="flex items-center justify-between border-t border-border pt-2 text-[10px] uppercase tracking-wider text-muted-foreground">
              <span>
                showing {visible.length} / {events.length}
                {filter ? ` · filtered by ${filter}` : ""}
              </span>
              <span>{stream.status}</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function StreamBadge({ state }: { state: StreamState }) {
  const map: Record<
    StreamState["status"],
    { label: string; className: string; icon: typeof Activity }
  > = {
    connecting: {
      label: "connecting",
      className: "border-info/40 bg-info/10 text-info",
      icon: Loader2,
    },
    streaming: {
      label: "live",
      className: "border-success/40 bg-success/10 text-success",
      icon: Activity,
    },
    closed: {
      label: "closed",
      className: "border-border bg-muted text-muted-foreground",
      icon: Pause,
    },
    error: {
      label: "error",
      className: "border-destructive/40 bg-destructive/10 text-destructive",
      icon: X,
    },
  };
  const e = map[state.status];
  const Icon = e.icon;
  const animate = state.status === "connecting" || state.status === "streaming";
  return (
    <span
      title={state.detail ?? undefined}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        e.className,
      )}
    >
      <Icon
        className={cn(
          "h-3 w-3",
          animate && state.status === "connecting" && "animate-spin",
          animate && state.status === "streaming" && "animate-pulse",
        )}
      />
      <span>{e.label}</span>
    </span>
  );
}

function FilterPill({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-card text-muted-foreground hover:border-foreground/30 hover:text-foreground",
      )}
    >
      <span>{label}</span>
      <span className="font-mono tabular-nums opacity-70">{count}</span>
    </button>
  );
}

function AuditEventRow({ event }: { event: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const hasPayload = Object.keys(event.payload ?? {}).length > 0;
  const tone =
    CATEGORY_TONE[event.category] ?? "border-border bg-muted text-muted-foreground";
  const time = new Date(event.ts).toLocaleTimeString(undefined, {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  });

  return (
    <li className="rounded-md border border-border bg-card/40 px-3 py-2">
      <button
        type="button"
        onClick={() => hasPayload && setOpen((o) => !o)}
        className={cn(
          "flex w-full items-center gap-2 text-left",
          hasPayload && "cursor-pointer",
        )}
      >
        {hasPayload ? (
          open ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          )
        ) : (
          <span className="h-3 w-3" aria-hidden />
        )}
        <span className="shrink-0 tabular-nums text-muted-foreground">
          {time}
        </span>
        <span
          className={cn(
            "shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium",
            tone,
          )}
        >
          {event.category}
        </span>
        <span className="truncate text-foreground">{event.event}</span>
      </button>
      {open && hasPayload ? (
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-secondary/60 p-2 text-[11px] leading-relaxed text-muted-foreground scrollbar-thin">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      ) : null}
    </li>
  );
}
