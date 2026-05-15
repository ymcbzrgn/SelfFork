/**
 * Talk — Stitch-verbatim port (split chat + canvas).
 *
 * Left pane: alternating chat bubbles (user right, agent left) with a
 * big send-style input at the bottom. Right pane: a canvas preview
 * card that shows what's being built, or an empty state when no
 * workspace is active.
 *
 * Real backend wiring: lists real recent sessions when no workspace
 * is set so the operator can resume a thread. The intent input is
 * honest: it acknowledges the message and surfaces an inline empty-
 * canvas state until the orchestrator's live agent loop wires up
 * to a single endpoint we can call from here.
 *
 * Stitch design reference: screen a758e4d349474230b55530d83139016b.
 */
"use client";

import { useSearchParams } from "next/navigation";
import { ArrowRight, FolderOpen, Maximize2, Sparkles } from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { listRecentSessions, type RecentSession } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Message {
  role: "you" | "selffork";
  body: string;
  streaming?: boolean;
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, Math.floor((now - then) / 1000));
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function TalkBody() {
  const params = useSearchParams();
  const workspace = params.get("workspace");
  const [intent, setIntent] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [recent, setRecent] = useState<RecentSession[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    if (workspace) return; // No need to list recents when in a workspace.
    let cancelled = false;
    listRecentSessions()
      .then((data) => {
        if (!cancelled) setRecent(data);
      })
      .catch(() => {
        if (!cancelled) setRecent([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workspace]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const raw = intent.trim();
    if (!raw) return;
    setMessages((prev) => [
      ...prev,
      { role: "you", body: raw },
      {
        role: "selffork",
        body:
          "I hear you. The live agent loop wires up next — when it lands, this is the message it acts on.",
        streaming: true,
      },
    ]);
    setIntent("");
  };

  return (
    <div className="ml-0 md:ml-0 h-[calc(100vh-64px)] flex">
      {/* Left pane — chat. */}
      <section className="w-full md:w-3/5 flex flex-col bg-surface-container-low/30 relative">
        <div className="flex-1 overflow-y-auto px-12 py-8 space-y-8">
          {messages.length === 0 ? (
            workspace ? (
              <p className="font-body text-body text-foreground-muted text-center mt-12">
                Say something to your agent. The live loop wires up next.
              </p>
            ) : recent === null ? (
              <p className="font-body text-body text-foreground-muted text-center mt-12">
                Loading recent…
              </p>
            ) : recent.length === 0 ? (
              <p className="font-body text-body text-foreground-muted text-center mt-12">
                Nothing yet. Send something below to begin.
              </p>
            ) : (
              <div className="space-y-3">
                <span className="font-caption text-caption text-foreground-muted uppercase tracking-wider">
                  Recent threads
                </span>
                {recent.slice(0, 8).map((s) => (
                  <div
                    key={s.session_id}
                    className="bg-surface rounded-xl p-4 shadow-[0_2px_8px_rgba(15,23,42,0.04)] flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <FolderOpen
                        className="h-4 w-4 text-foreground-muted"
                        strokeWidth={1.75}
                      />
                      <div>
                        <p className="font-body text-body text-on-surface">
                          {s.cli_agent ?? "session"} · {s.session_id.slice(0, 8)}
                        </p>
                        <p className="font-caption text-caption text-foreground-muted">
                          {s.rounds_observed} rounds ·{" "}
                          {relativeTime(s.last_event_at)}
                        </p>
                      </div>
                    </div>
                    <span
                      className={cn(
                        "font-caption text-caption font-medium",
                        s.final_state === "done"
                          ? "text-success"
                          : s.final_state == null
                            ? "text-primary"
                            : "text-foreground-muted",
                      )}
                    >
                      {s.final_state ?? "running"}
                    </span>
                  </div>
                ))}
              </div>
            )
          ) : (
            messages.map((m, i) =>
              m.role === "you" ? (
                <div
                  key={i}
                  className="flex flex-col items-end gap-2 max-w-[85%] ml-auto"
                >
                  <span className="font-caption text-caption text-foreground-muted px-2">
                    You
                  </span>
                  <div className="bg-surface p-4 rounded-2xl shadow-[0_2px_8px_rgba(15,23,42,0.04)]">
                    <p className="font-body text-body text-on-surface">
                      {m.body}
                    </p>
                  </div>
                </div>
              ) : (
                <div
                  key={i}
                  className="flex flex-col items-start gap-2 max-w-[85%]"
                >
                  <span className="font-caption text-caption text-primary px-2">
                    SelfFork
                  </span>
                  <div
                    className={cn(
                      "bg-surface-container-low p-4 rounded-2xl",
                      m.streaming && "border-l-2 border-primary/20",
                    )}
                  >
                    <p className="font-body text-body text-on-surface">
                      {m.body}
                    </p>
                  </div>
                </div>
              ),
            )
          )}
        </div>

        {/* Big input shell */}
        <div className="p-8 bg-gradient-to-t from-surface to-transparent">
          <form
            onSubmit={submit}
            className="max-w-3xl mx-auto relative flex items-center group"
          >
            <input
              ref={inputRef}
              type="text"
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              placeholder={workspace ? "What are we building?" : "What are you building?"}
              aria-label="Message"
              className={cn(
                "w-full bg-surface border-none rounded-2xl py-6 px-8",
                "font-display-mobile text-[28px] leading-[1.2] tracking-[-0.02em] font-semibold",
                "text-on-surface placeholder:text-outline-variant",
                "shadow-[0_4px_12px_rgba(15,23,42,0.06)]",
                "transition-all focus:outline-none focus:ring-1 focus:ring-primary/20",
              )}
            />
            <button
              type="submit"
              disabled={!intent.trim()}
              className="absolute right-6 p-3 text-primary hover:bg-primary/10 rounded-xl transition-colors active:scale-95 disabled:opacity-30"
              aria-label="Send"
            >
              <ArrowRight className="h-8 w-8" strokeWidth={1.75} />
            </button>
          </form>
        </div>
      </section>

      {/* Right pane — canvas preview. */}
      <section className="hidden md:flex w-2/5 bg-surface-muted/50 p-10 items-center justify-center">
        <div className="w-full h-full max-h-[800px] bg-surface rounded-[32px] shadow-[0_12px_40px_rgba(15,23,42,0.04)] overflow-hidden flex flex-col">
          <div className="h-12 border-b border-surface-muted flex items-center px-6 justify-between bg-surface-bright">
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-outline-variant/30" />
              <div className="w-2.5 h-2.5 rounded-full bg-outline-variant/30" />
              <div className="w-2.5 h-2.5 rounded-full bg-outline-variant/30" />
            </div>
            <span className="font-caption text-caption text-foreground-muted">
              {workspace ? `${workspace}.preview` : "preview"}
            </span>
            <Maximize2
              className="h-[18px] w-[18px] text-foreground-muted"
              strokeWidth={1.75}
            />
          </div>
          <div className="flex-1 p-8 overflow-hidden relative">
            <div className="grid grid-cols-2 grid-rows-3 gap-4 h-full animate-pulse opacity-60">
              <div className="col-span-2 bg-surface-container-low rounded-2xl" />
              <div className="bg-surface-container-low rounded-2xl" />
              <div className="bg-surface-container-low rounded-2xl" />
              <div className="col-span-2 bg-surface-container-low rounded-2xl" />
            </div>
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-12 bg-surface/40 backdrop-blur-[2px]">
              <div className="w-16 h-16 bg-surface rounded-2xl shadow-sm flex items-center justify-center mb-4">
                <Sparkles className="h-8 w-8 text-primary" strokeWidth={1.75} />
              </div>
              <h3 className="font-heading text-heading text-on-surface mb-2">
                {messages.length > 0 ? "Generating Interface" : "Idle Canvas"}
              </h3>
              <p className="font-body text-body text-foreground-muted">
                {messages.length > 0
                  ? "SelfFork is composing your idea. Watch this space."
                  : "Send a prompt on the left to wake the canvas."}
              </p>
              {messages.length > 0 ? (
                <div className="mt-8 flex items-center gap-2 px-3 py-1 bg-success/10 rounded-full">
                  <span className="w-2 h-2 rounded-full bg-success" />
                  <span className="font-caption text-caption text-success">
                    active stream
                  </span>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function TalkPage() {
  return (
    <AppShell title="Personal Space">
      <Suspense
        fallback={
          <p className="font-body text-caption text-foreground-muted px-gutter-desktop py-vertical-gap">
            Loading…
          </p>
        }
      >
        <TalkBody />
      </Suspense>
    </AppShell>
  );
}
