/**
 * Run tab root — Order 7.
 *
 * Lays out: session selector + paradigm toggle + filter chips, then
 * the AuditStream below either the TraceTree or the Waterfall view.
 * Order 9's E2E smoke walks this tab against a real PRD run.
 */
"use client";

import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  getSessionEvents,
  listRecentSessions,
  type AuditEvent,
  type RecentSession,
} from "@/lib/api";
import { cockpitKeys } from "@/lib/query";
import { useCockpitStore } from "@/lib/store";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";

import { AuditStream } from "./AuditStream";
import { FilterChips } from "./FilterChips";
import { ParadigmToggle } from "./ParadigmToggle";
import { TraceTree } from "./TraceTree";
import { Waterfall } from "./Waterfall";

export function RunTab() {
  const sessionsQuery = useQuery<RecentSession[]>({
    queryKey: cockpitKeys.recentSessions(),
    queryFn: listRecentSessions,
  });
  const activeSessionId = useCockpitStore((s) => s.runActiveSessionId);
  const setActiveSession = useCockpitStore((s) => s.setRunActiveSession);
  const paradigm = useCockpitStore((s) => s.runParadigm);

  useEffect(() => {
    if (
      activeSessionId === null &&
      sessionsQuery.data &&
      sessionsQuery.data.length > 0
    ) {
      setActiveSession(sessionsQuery.data[0].session_id);
    }
  }, [activeSessionId, sessionsQuery.data, setActiveSession]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SessionPicker
          sessions={sessionsQuery.data ?? []}
          activeId={activeSessionId}
          onChange={setActiveSession}
          loading={sessionsQuery.isPending}
        />
        <ParadigmToggle />
      </div>
      <FilterChips />
      <RunBody activeSessionId={activeSessionId} paradigm={paradigm} />
    </div>
  );
}

function SessionPicker({
  sessions,
  activeId,
  loading,
  onChange,
}: {
  sessions: RecentSession[];
  activeId: string | null;
  loading: boolean;
  onChange: (id: string | null) => void;
}) {
  if (loading) return <Skeleton className="h-9 w-72" />;
  if (sessions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No recent sessions. Start one from the Mission tab or
        <code className="font-mono"> selffork run</code>.
      </p>
    );
  }
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Session</span>
      <select
        aria-label="Active session"
        value={activeId ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="rounded-md border border-border bg-card px-2 py-1 text-sm"
      >
        {sessions.map((s) => (
          <option key={s.session_id} value={s.session_id}>
            {s.session_id} ({s.cli_agent ?? "?"} · {s.final_state ?? "?"})
          </option>
        ))}
      </select>
    </label>
  );
}

function RunBody({
  activeSessionId,
  paradigm,
}: {
  activeSessionId: string | null;
  paradigm: "trace" | "waterfall";
}) {
  if (activeSessionId === null) {
    return (
      <EmptyState
        title="No session selected"
        hint="Pick a session above to load its audit stream."
      />
    );
  }
  return (
    <SessionRunBody sessionId={activeSessionId} paradigm={paradigm} />
  );
}

function SessionRunBody({
  sessionId,
  paradigm,
}: {
  sessionId: string;
  paradigm: "trace" | "waterfall";
}) {
  const eventsQuery = useQuery<AuditEvent[]>({
    queryKey: cockpitKeys.audit(sessionId),
    queryFn: () => getSessionEvents(sessionId),
  });

  const filterTool = useCockpitStore((s) => s.runFilterTool);
  const filterCli = useCockpitStore((s) => s.runFilterCli);
  const filterCategory = useCockpitStore((s) => s.runFilterCategory);
  const search = useCockpitStore((s) => s.runSearchQuery);

  // Keep round-context events (agent.invoke / agent.output / agent.done /
  // selffork_jr.reply) visible even when a tool filter is active so the
  // trace tree doesn't render a child without its parent (Order 7 audit
  // fix). The user's tool intent narrows ``tool.call`` / ``tool.result``
  // events; their surrounding round skeleton stays in the stream.
  const ROUND_CONTEXT_CATEGORIES = useMemo(
    () =>
      new Set([
        "agent.invoke",
        "agent.output",
        "agent.done",
        "agent.rate_limited",
        "selffork_jr.reply",
      ]),
    [],
  );

  const filtered = useMemo(() => {
    const events = eventsQuery.data ?? [];
    const lowered = search.trim().toLowerCase();
    return events.filter((ev) => {
      const isRoundContext = ROUND_CONTEXT_CATEGORIES.has(ev.category);
      if (filterCategory && ev.category !== filterCategory) return false;
      if (filterTool) {
        const evTool = ev.payload.tool as string | undefined;
        if (evTool !== filterTool && !isRoundContext) return false;
      }
      if (filterCli) {
        const binary = ev.payload.binary as string | undefined;
        if (!binary?.includes(filterCli) && !isRoundContext) return false;
      }
      if (lowered) {
        const haystack = JSON.stringify(ev).toLowerCase();
        if (!haystack.includes(lowered)) return false;
      }
      return true;
    });
  }, [
    eventsQuery.data,
    filterTool,
    filterCli,
    filterCategory,
    search,
    ROUND_CONTEXT_CATEGORIES,
  ]);

  if (eventsQuery.isPending) {
    return <Skeleton className="h-96 w-full" data-testid="run-loading" />;
  }
  if (eventsQuery.isError) {
    return (
      <ErrorState
        title="Could not load audit stream"
        detail={String(eventsQuery.error)}
      />
    );
  }

  return (
    <div className="space-y-4">
      <AuditStream sessionId={sessionId} events={filtered} />
      {paradigm === "trace" ? (
        <TraceTree events={filtered} />
      ) : (
        <Waterfall events={filtered} />
      )}
    </div>
  );
}
