/**
 * Dashboard home — KPI strip + paused-sessions list + recent-sessions table.
 *
 * Every tile and row is fed by a real backend endpoint; we never insert
 * placeholder values. When an endpoint is empty we render an EmptyState
 * rather than hiding the section, so the user always sees what's there.
 */
"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  ListTree,
  PauseCircle,
  Play,
  RefreshCw,
  Terminal,
  Timer,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import {
  RelativeAge,
  RelativeFuture,
  ShortSessionId,
} from "@/components/format";
import { KpiCard } from "@/components/kpi-card";
import { StatusBadge, type SessionStateName } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type PausedSession,
  type RecentSession,
  listPausedSessions,
  listRecentSessions,
  resumeNow,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface DataState<T> {
  status: "loading" | "ok" | "error";
  data: T | null;
  error: string | null;
}

function useDashboardData() {
  const [paused, setPaused] = useState<DataState<PausedSession[]>>({
    status: "loading",
    data: null,
    error: null,
  });
  const [recent, setRecent] = useState<DataState<RecentSession[]>>({
    status: "loading",
    data: null,
    error: null,
  });

  const refresh = useCallback(async () => {
    try {
      const data = await listPausedSessions();
      setPaused({ status: "ok", data, error: null });
    } catch (e) {
      setPaused({
        status: "error",
        data: null,
        error: e instanceof Error ? e.message : String(e),
      });
    }
    try {
      const data = await listRecentSessions();
      setRecent({ status: "ok", data, error: null });
    } catch (e) {
      setRecent({
        status: "error",
        data: null,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), 5_000);
    return () => clearInterval(t);
  }, [refresh]);

  return { paused, recent, refresh };
}

export default function DashboardPage() {
  const { paused, recent, refresh } = useDashboardData();

  return (
    <AppShell title="Dashboard">
      <div className="space-y-8">
        <DashboardHeader onRefresh={() => void refresh()} />
        <KpiStrip paused={paused} recent={recent} />
        <PausedSessionsCard state={paused} onResumed={() => void refresh()} />
        <RecentSessionsCard state={recent} />
      </div>
    </AppShell>
  );
}

// ── Header ────────────────────────────────────────────────────────────────────

function DashboardHeader({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">
          SelfFork sessions
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Live view of every session SelfFork has on disk. Auto-refreshes
          every 5 seconds.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Link
          href="/run/"
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Play className="h-4 w-4" />
          New run
        </Link>
        <Button variant="outline" size="sm" onClick={onRefresh}>
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>
    </div>
  );
}

// ── KPI strip ─────────────────────────────────────────────────────────────────

function KpiStrip({
  paused,
  recent,
}: {
  paused: DataState<PausedSession[]>;
  recent: DataState<RecentSession[]>;
}) {
  const pausedCount =
    paused.status === "ok" ? (paused.data?.length ?? 0) : null;
  const dueNow =
    paused.status === "ok"
      ? (paused.data ?? []).filter((p) => p.is_due).length
      : null;
  const recentCount =
    recent.status === "ok" ? (recent.data?.length ?? 0) : null;
  const lastEventTs = useMemo(() => {
    if (recent.status !== "ok" || !recent.data || recent.data.length === 0) {
      return null;
    }
    return [...recent.data].sort(
      (a, b) =>
        new Date(b.last_event_at).getTime() -
        new Date(a.last_event_at).getTime(),
    )[0].last_event_at;
  }, [recent]);

  const completed =
    recent.status === "ok"
      ? (recent.data ?? []).filter((r) => r.final_state === "completed").length
      : null;

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <KpiCard
        label="Paused"
        value={pausedCount ?? "—"}
        hint={
          dueNow !== null && dueNow > 0
            ? `${dueNow} due now`
            : pausedCount === 0
              ? "no sessions waiting"
              : "subscription window"
        }
        icon={PauseCircle}
        tone={dueNow !== null && dueNow > 0 ? "warning" : "default"}
      />
      <KpiCard
        label="Sessions"
        value={recentCount ?? "—"}
        hint="audit logs on disk"
        icon={ListTree}
      />
      <KpiCard
        label="Completed"
        value={completed ?? "—"}
        hint={
          completed !== null && recentCount !== null && recentCount > 0
            ? `${Math.round((completed / recentCount) * 100)}% of all`
            : undefined
        }
        icon={Terminal}
        tone={
          completed !== null && completed > 0 ? "success" : "default"
        }
      />
      <KpiCard
        label="Last event"
        value={
          lastEventTs ? <KpiRelative isoTs={lastEventTs} /> : "—"
        }
        hint={lastEventTs ?? "no events yet"}
        icon={Timer}
        tone="info"
      />
    </div>
  );
}

function KpiRelative({ isoTs }: { isoTs: string }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  if (now === null) return <span>…</span>;
  const diff = Math.floor((now.getTime() - new Date(isoTs).getTime()) / 1000);
  if (diff < 60) return <span>{diff}s</span>;
  if (diff < 3600) return <span>{Math.floor(diff / 60)}m</span>;
  if (diff < 86400) return <span>{Math.floor(diff / 3600)}h</span>;
  return <span>{Math.floor(diff / 86400)}d</span>;
}

// ── Paused sessions ───────────────────────────────────────────────────────────

function PausedSessionsCard({
  state,
  onResumed,
}: {
  state: DataState<PausedSession[]>;
  onResumed: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2">
            <PauseCircle className="h-4 w-4 text-warning" />
            Paused sessions
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Waiting for a subscription window to reopen. Run{" "}
            <code className="font-mono">selffork resume watch</code> on the
            host to auto-resume due records.
          </p>
        </div>
        {state.status === "ok" ? (
          <Badge variant="outline" className="font-mono">
            {(state.data ?? []).length}
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent>
        {state.status === "loading" ? (
          <SkeletonRowList />
        ) : state.status === "error" ? (
          <ErrorState
            title="Couldn't load paused sessions"
            detail={state.error ?? undefined}
          />
        ) : (state.data ?? []).length === 0 ? (
          <EmptyState
            title="No paused sessions"
            hint="When a CLI agent hits its rate limit, the session gets parked here."
          />
        ) : (
          <ul className="divide-y divide-border">
            {(state.data ?? []).map((row) => (
              <PausedRow key={row.session_id} row={row} onResumed={onResumed} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PausedRow({
  row,
  onResumed,
}: {
  row: PausedSession;
  onResumed: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [pidNote, setPidNote] = useState<string | null>(null);

  return (
    <li className="grid grid-cols-1 items-center gap-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:gap-4">
      <div className="min-w-0 space-y-1">
        <Link
          href={`/session/?id=${row.session_id}`}
          className="inline-flex items-center gap-1.5 hover:underline"
        >
          <ShortSessionId id={row.session_id} />
          <ArrowUpRight className="h-3 w-3 text-muted-foreground" />
        </Link>
        <p className="truncate text-xs text-muted-foreground">{row.reason}</p>
        <p className="truncate font-mono text-[11px] text-muted-foreground/80">
          prd: {row.prd_path}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium",
            row.is_due
              ? "border-warning/40 bg-warning/10 text-warning"
              : "border-info/30 bg-info/5 text-info",
          )}
        >
          {row.is_due ? (
            <>
              <PauseCircle className="h-3 w-3" />
              <span>due now</span>
            </>
          ) : (
            <>
              <Timer className="h-3 w-3" />
              <span className="font-mono">
                <RelativeFuture isoTs={row.resume_at} />
              </span>
            </>
          )}
        </span>
        <Badge variant="outline">{row.cli_agent}</Badge>
        <Badge variant="outline">{row.kind}</Badge>
        <Button
          size="sm"
          variant="default"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setPidNote(null);
            try {
              const res = await resumeNow(row.session_id);
              setPidNote(
                res.status === "started"
                  ? `pid=${res.pid}`
                  : (res.detail ?? res.status),
              );
              onResumed();
            } catch (e) {
              setPidNote(e instanceof Error ? e.message : String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          <Play className="h-3.5 w-3.5" />
          {busy ? "Resuming…" : "Resume now"}
        </Button>
        {pidNote ? (
          <span className="ml-1 truncate text-[11px] text-muted-foreground">
            {pidNote}
          </span>
        ) : null}
      </div>
    </li>
  );
}

// ── Recent sessions table ─────────────────────────────────────────────────────

type SortKey = "last_event_at" | "started_at" | "rounds_observed";

function RecentSessionsCard({ state }: { state: DataState<RecentSession[]> }) {
  const [sortKey, setSortKey] = useState<SortKey>("last_event_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const rows = useMemo(() => {
    if (state.data === null) return null;
    const sorted = [...state.data];
    sorted.sort((a, b) => {
      const av = sortKey === "rounds_observed"
        ? a.rounds_observed
        : new Date(a[sortKey]).getTime();
      const bv = sortKey === "rounds_observed"
        ? b.rounds_observed
        : new Date(b[sortKey]).getTime();
      return sortDir === "asc" ? av - bv : bv - av;
    });
    return sorted;
  }, [state.data, sortKey, sortDir]);

  const onSort = (k: SortKey) => {
    if (k === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setSortDir("desc");
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2">
            <ListTree className="h-4 w-4 text-muted-foreground" />
            Recent sessions
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Every session whose audit log lives under{" "}
            <code className="font-mono">~/.selffork/audit/</code>.
          </p>
        </div>
        {state.status === "ok" ? (
          <Badge variant="outline" className="font-mono">
            {(state.data ?? []).length}
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className="px-0 pt-0">
        {state.status === "loading" ? (
          <div className="px-6 py-4">
            <SkeletonRowList />
          </div>
        ) : state.status === "error" ? (
          <div className="px-6 py-4">
            <ErrorState
              title="Couldn't load recent sessions"
              detail={state.error ?? undefined}
            />
          </div>
        ) : (rows ?? []).length === 0 ? (
          <div className="px-6 py-4">
            <EmptyState
              title="No sessions yet"
              hint={
                <>
                  Run <code>selffork run &lt;prd&gt;</code> in a terminal
                  to produce your first audit log.
                </>
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full border-separate border-spacing-0 text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="border-y border-border px-6 py-2 font-medium">
                    Session
                  </th>
                  <SortableTh
                    label="Started"
                    active={sortKey === "started_at"}
                    dir={sortDir}
                    onClick={() => onSort("started_at")}
                  />
                  <SortableTh
                    label="Last event"
                    active={sortKey === "last_event_at"}
                    dir={sortDir}
                    onClick={() => onSort("last_event_at")}
                  />
                  <SortableTh
                    label="Rounds"
                    active={sortKey === "rounds_observed"}
                    dir={sortDir}
                    onClick={() => onSort("rounds_observed")}
                    className="w-24"
                  />
                  <th className="border-y border-border px-6 py-2 font-medium">
                    CLI
                  </th>
                  <th className="border-y border-border px-6 py-2 font-medium">
                    State
                  </th>
                </tr>
              </thead>
              <tbody>
                {(rows ?? []).map((row) => (
                  <tr
                    key={row.session_id}
                    className="group border-border transition-colors hover:bg-secondary/40"
                  >
                    <td className="border-b border-border px-6 py-2.5 font-mono text-xs">
                      <Link
                        href={`/session/?id=${row.session_id}`}
                        className="inline-flex items-center gap-1.5 hover:underline"
                      >
                        <ShortSessionId id={row.session_id} />
                        <ArrowUpRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100" />
                      </Link>
                    </td>
                    <td className="border-b border-border px-6 py-2.5 text-muted-foreground">
                      <RelativeAge isoTs={row.started_at} />
                    </td>
                    <td className="border-b border-border px-6 py-2.5 text-muted-foreground">
                      <RelativeAge isoTs={row.last_event_at} />
                    </td>
                    <td className="border-b border-border px-6 py-2.5 font-mono tabular-nums">
                      {row.rounds_observed}
                    </td>
                    <td className="border-b border-border px-6 py-2.5">
                      {row.cli_agent ? (
                        <Badge variant="outline">{row.cli_agent}</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="border-b border-border px-6 py-2.5">
                      <StatusBadge
                        state={row.final_state as SessionStateName | null}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SortableTh({
  label,
  active,
  dir,
  onClick,
  className,
}: {
  label: string;
  active: boolean;
  dir: "asc" | "desc";
  onClick: () => void;
  className?: string;
}) {
  return (
    <th
      className={cn(
        "border-y border-border px-6 py-2 font-medium",
        className,
      )}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 transition-colors hover:text-foreground",
          active && "text-foreground",
        )}
      >
        <span>{label}</span>
        {active ? (
          <span aria-hidden className="text-[10px]">
            {dir === "asc" ? "▲" : "▼"}
          </span>
        ) : (
          <span aria-hidden className="text-[10px] opacity-30">
            ↕
          </span>
        )}
      </button>
    </th>
  );
}

function SkeletonRowList() {
  return (
    <ul className="space-y-3">
      {[0, 1, 2].map((i) => (
        <li key={i} className="flex items-center justify-between gap-4">
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-64" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-7 w-24" />
          </div>
        </li>
      ))}
    </ul>
  );
}
