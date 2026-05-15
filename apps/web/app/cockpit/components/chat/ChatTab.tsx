/**
 * Chat tab root — Order 8.
 *
 * Layout: session picker + branch picker / input. Subscribes to the
 * chat WS and pushes new messages into the TanStack Query cache so
 * the MessageList re-renders without polling.
 */
"use client";

import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  chatStreamUrl,
  listBranches,
  listMessages,
  listRecentSessions,
  setActiveBranch as patchActiveBranch,
  type BranchResponse,
  type ChatMessageResponse,
  type RecentSession,
} from "@/lib/api";
import { cockpitKeys, queryClient } from "@/lib/query";
import { useCockpitStore } from "@/lib/store";
import { useWebsocketSubscription } from "@/lib/ws/multiplex";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";

import { BranchPicker } from "./BranchPicker";
import { MessageInput } from "./MessageInput";
import { MessageList } from "./MessageList";

export function ChatTab() {
  const sessionsQuery = useQuery<RecentSession[]>({
    queryKey: cockpitKeys.recentSessions(),
    queryFn: listRecentSessions,
  });
  const activeSessionId = useCockpitStore((s) => s.chatActiveSessionId);
  const setActiveSession = useCockpitStore((s) => s.setChatActiveSession);

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
      <SessionPicker
        sessions={sessionsQuery.data ?? []}
        activeId={activeSessionId}
        onChange={setActiveSession}
        loading={sessionsQuery.isPending}
      />
      <ChatBody activeSessionId={activeSessionId} />
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
        No sessions yet — start one from the Mission tab.
      </p>
    );
  }
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Session</span>
      <select
        aria-label="Active chat session"
        value={activeId ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="rounded-md border border-border bg-card px-2 py-1 text-sm"
      >
        {sessions.map((s) => (
          <option key={s.session_id} value={s.session_id}>
            {s.session_id} ({s.cli_agent ?? "?"})
          </option>
        ))}
      </select>
    </label>
  );
}

function ChatBody({ activeSessionId }: { activeSessionId: string | null }) {
  if (activeSessionId === null) {
    return (
      <EmptyState
        title="No session selected"
        hint="Pick a session above to load chat history."
      />
    );
  }
  return <ChatSession sessionId={activeSessionId} />;
}

function ChatSession({ sessionId }: { sessionId: string }) {
  const branchesQuery = useQuery<BranchResponse[]>({
    queryKey: cockpitKeys.branches(sessionId),
    queryFn: () => listBranches(sessionId),
  });
  const activeBranchFromStore = useCockpitStore(
    (s) => s.chatActiveBranchId,
  );
  const setActiveBranchInStore = useCockpitStore(
    (s) => s.setChatActiveBranch,
  );

  const activeBranchId = useMemo(() => {
    if (activeBranchFromStore !== null) return activeBranchFromStore;
    return (
      branchesQuery.data?.find((b) => b.is_active)?.id ?? null
    );
  }, [activeBranchFromStore, branchesQuery.data]);

  const messagesQuery = useQuery<ChatMessageResponse[]>({
    queryKey: cockpitKeys.messages(sessionId, activeBranchId),
    queryFn: () => listMessages(sessionId, activeBranchId ?? undefined),
    enabled: branchesQuery.isSuccess,
  });

  useWebsocketSubscription({
    url: chatStreamUrl(sessionId),
    onEnvelope: (env) => {
      if (env.event_type !== "chat.token") return;
      const branchId = String(env.payload.branch_id ?? "");
      const messageId = String(env.payload.message_id ?? "");
      if (!branchId || !messageId) return;
      // Push the new message into whichever branch's cache it lands.
      queryClient.setQueryData<ChatMessageResponse[]>(
        cockpitKeys.messages(sessionId, branchId),
        (prev) => {
          const copy = [...(prev ?? [])];
          if (copy.find((m) => m.id === messageId)) return copy;
          copy.push({
            id: messageId,
            branch_id: branchId,
            role: (env.payload.role as ChatMessageResponse["role"]) ?? "user",
            content: String(env.payload.content ?? ""),
            parent_message_id: null,
            created_at: String(env.payload.created_at ?? new Date().toISOString()),
          });
          return copy;
        },
      );
    },
  });

  const onSelectBranch = async (id: string) => {
    setActiveBranchInStore(id);
    try {
      await patchActiveBranch(sessionId, id);
    } catch {
      // Server-side switch is best-effort; the UI honours the local
      // selection regardless so the operator isn't blocked on flaky
      // network. Background reconcile happens on next refresh.
    }
    void queryClient.invalidateQueries({
      queryKey: cockpitKeys.branches(sessionId),
    });
  };

  const onSubmitted = () => {
    void queryClient.invalidateQueries({
      queryKey: cockpitKeys.messages(sessionId, activeBranchId),
    });
    void queryClient.invalidateQueries({
      queryKey: cockpitKeys.branches(sessionId),
    });
  };

  if (branchesQuery.isPending || messagesQuery.isPending) {
    return <Skeleton className="h-96 w-full" data-testid="chat-loading" />;
  }
  return (
    <div className="space-y-4">
      <BranchPicker
        branches={branchesQuery.data ?? []}
        activeBranchId={activeBranchId}
        onSelect={(id) => void onSelectBranch(id)}
        forkMessageId={
          // Picker scopes to siblings of the current branch's fork
          // point — ``branches.find(b => b.id === activeBranchId)``
          // safely tolerates ``activeBranchId === null`` (find returns
          // undefined → undefined cascade → unfiltered fallback).
          branchesQuery.data?.find((b) => b.id === activeBranchId)
            ?.fork_message_id ?? null
        }
      />
      <MessageList messages={messagesQuery.data ?? []} />
      <MessageInput
        sessionId={sessionId}
        branchId={activeBranchId}
        onSubmitted={onSubmitted}
      />
    </div>
  );
}
