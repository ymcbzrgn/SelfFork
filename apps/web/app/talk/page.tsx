"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  History,
  Loader2,
  MessageCircle,
  Paperclip,
  Plus,
} from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import {
  ChatMessage,
  type ChatMessageView,
} from "@/components/talk/ChatMessage";
import {
  claimTelegramDrafts,
  getTalkConversation,
  listProjects,
  listTalkConversations,
  listTelegramDrafts,
  openTalkStream,
  sendTalkMessage,
  type ConversationResponse,
  type ProjectResponse,
  type TalkMessageResponse,
  type TelegramDraftResponse,
} from "@/lib/api";

const SLASH_CHIPS = ["/cli", "/workspace", "/pause", "/note", "/finetune"];

const SPEAKER_NOTICE: Record<string, string> = {
  offline:
    "Self Jr is offline — the model endpoint is unreachable. Your message was saved.",
  not_configured:
    "No model endpoint is configured yet. Your message was saved; set an endpoint to get replies.",
};

const EXAMPLE_PROMPTS = [
  "What did Self Jr ship today?",
  "Switch ProjectX to Codex",
  "Pause everything for an hour",
];

interface TalkMessagePayload {
  conversation_id: string;
  message_id: string;
  seq: number;
  role: "operator" | "self_jr";
  content: string;
  created_at: string;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function messageToView(m: TalkMessageResponse): ChatMessageView {
  return {
    id: m.id,
    role: m.role,
    text: m.content,
    ts: formatTime(m.created_at),
  };
}

function useTelegramDrafts() {
  const [drafts, setDrafts] = useState<TelegramDraftResponse[]>([]);
  const refresh = useCallback(() => {
    listTelegramDrafts()
      .then(setDrafts)
      .catch(() => setDrafts([]));
  }, []);
  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 30_000);
    return () => window.clearInterval(id);
  }, [refresh]);
  const claim = useCallback(
    (ids: number[]) =>
      claimTelegramDrafts(ids)
        .then(() => refresh())
        .catch(() => undefined),
    [refresh],
  );
  return { drafts, claim };
}

export default function TalkPage() {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [contextSlug, setContextSlug] = useState<string | null>(null);
  const { drafts: telegramDrafts, claim: claimTelegramDraftIds } =
    useTelegramDrafts();
  const [conversations, setConversations] = useState<ConversationResponse[]>(
    [],
  );
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageView[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [speakerStatus, setSpeakerStatus] = useState<string | null>(null);
  const [openContextMenu, setOpenContextMenu] = useState(false);
  const [openHistory, setOpenHistory] = useState(false);
  const feedEndRef = useRef<HTMLDivElement | null>(null);
  // Live mirror of conversationId — lets an in-flight onSend detect a
  // conversation switch and discard its now-stale result.
  const conversationIdRef = useRef<string | null>(null);

  // Mount — load projects + conversations; pick which conversation shows.
  useEffect(() => {
    listProjects()
      .then((p) => {
        setProjects(p);
        if (p[0]) setContextSlug(p[0].slug);
      })
      .catch(() => {});

    const wantsNew =
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("intent") ===
        "new-workspace";

    listTalkConversations()
      .then((list) => {
        setConversations(list);
        if (!wantsNew && list[0]) setConversationId(list[0].id);
      })
      .catch(() => {});
  }, []);

  // Selected conversation — load the thread + open the live stream.
  useEffect(() => {
    conversationIdRef.current = conversationId;
    if (!conversationId) {
      setMessages([]);
      return;
    }
    let cancelled = false;

    getTalkConversation(conversationId)
      .then((thread) => {
        if (!cancelled) setMessages(thread.messages.map(messageToView));
      })
      .catch(() => {});

    const ws = openTalkStream(conversationId);
    ws.onmessage = (ev) => {
      try {
        const env = JSON.parse(ev.data as string) as {
          event_type?: string;
          payload?: TalkMessagePayload;
        };
        if (env.event_type !== "talk.message" || !env.payload) return;
        const p = env.payload;
        setMessages((prev) =>
          prev.some((m) => m.id === p.message_id)
            ? prev
            : [
                ...prev,
                {
                  id: p.message_id,
                  role: p.role,
                  text: p.content,
                  ts: formatTime(p.created_at),
                },
              ],
        );
      } catch {
        // ignore malformed frames
      }
    };

    return () => {
      cancelled = true;
      if (ws.readyState !== WebSocket.CLOSED) ws.close();
    };
  }, [conversationId]);

  // Keep the newest message in view.
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const contextLabel = useMemo(() => {
    if (!contextSlug) return "All projects";
    return projects.find((x) => x.slug === contextSlug)?.name ?? contextSlug;
  }, [contextSlug, projects]);

  const onSend = useCallback(async () => {
    const text = draft.trim();
    if (!text || sending) return;
    // The conversation this send belongs to — if the operator switches
    // conversations while the request is in flight, the result is stale
    // and must be discarded (the thread-load effect guards itself too).
    const sentFor = conversationId;
    setSending(true);
    setSpeakerStatus(null);
    setDraft("");
    try {
      const res = await sendTalkMessage({
        text,
        conversation_id: sentFor ?? undefined,
        workspace: contextSlug ?? undefined,
      });
      if (conversationIdRef.current !== sentFor) return;
      setSpeakerStatus(res.speaker_status);
      if (res.conversation_id !== sentFor) {
        // A new conversation was created — switch to it (the effect
        // loads its thread + opens the stream) and refresh History.
        setConversationId(res.conversation_id);
        listTalkConversations()
          .then(setConversations)
          .catch(() => {});
      }
    } catch {
      if (conversationIdRef.current === sentFor) setSpeakerStatus("offline");
    } finally {
      setSending(false);
    }
  }, [draft, sending, conversationId, contextSlug]);

  const onNewChat = () => {
    setConversationId(null);
    setMessages([]);
    setSpeakerStatus(null);
    setDraft("");
    setOpenHistory(false);
  };

  const selectConversation = (id: string) => {
    setConversationId(id);
    setSpeakerStatus(null);
    setOpenHistory(false);
  };

  const showEmpty = messages.length === 0 && !sending;
  const notice = speakerStatus ? SPEAKER_NOTICE[speakerStatus] : undefined;

  return (
    <AppShell title="Talk">
      <div className="flex flex-col min-h-[calc(100vh-theme(spacing.topbar-height))] bg-background relative">
        <header className="px-gutter-desktop pt-vertical-gap max-w-3xl mx-auto w-full">
          <div className="flex items-start justify-between flex-wrap gap-3">
            <div>
              <h1 className="font-display text-display text-on-surface">
                Talk
              </h1>
              <div className="font-body text-caption text-on-surface-variant mt-1 flex items-center gap-2 flex-wrap">
                <span>Speaker: Self Jr · Context:</span>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setOpenContextMenu((x) => !x)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-surface-container-low rounded-md font-medium text-on-surface hover:bg-surface-container transition-colors"
                    aria-haspopup="listbox"
                    aria-expanded={openContextMenu}
                  >
                    {`Auto-detect (${contextLabel})`}
                    <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
                  </button>
                  {openContextMenu && (
                    <div
                      role="listbox"
                      className="absolute top-full left-0 mt-1 w-64 bg-surface rounded-lg shadow-lg border border-outline-variant/30 py-1 z-30 max-h-72 overflow-y-auto"
                    >
                      <button
                        role="option"
                        aria-selected={contextSlug === null}
                        onClick={() => {
                          setContextSlug(null);
                          setOpenContextMenu(false);
                        }}
                        className="w-full text-left px-3 py-1.5 text-caption hover:bg-surface-container-low"
                      >
                        All projects
                      </button>
                      {projects.map((p) => (
                        <button
                          key={p.slug}
                          role="option"
                          aria-selected={contextSlug === p.slug}
                          onClick={() => {
                            setContextSlug(p.slug);
                            setOpenContextMenu(false);
                          }}
                          className="w-full text-left px-3 py-1.5 text-caption hover:bg-surface-container-low"
                        >
                          {p.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onNewChat}
                className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg hover:bg-surface-container-low flex items-center gap-1"
              >
                <Plus className="h-4 w-4" strokeWidth={1.75} />
                New chat
              </button>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setOpenHistory((x) => !x)}
                  className="px-3 py-1.5 text-on-surface-variant hover:bg-surface-container-low text-caption font-medium rounded-lg flex items-center gap-1"
                  aria-haspopup="listbox"
                  aria-expanded={openHistory}
                >
                  <History className="h-4 w-4" strokeWidth={1.75} />
                  History
                </button>
                {openHistory && (
                  <div
                    role="listbox"
                    className="absolute top-full right-0 mt-1 w-72 bg-surface rounded-lg shadow-lg border border-outline-variant/30 py-1 z-30 max-h-80 overflow-y-auto"
                  >
                    {conversations.length === 0 ? (
                      <p className="px-3 py-2 text-caption text-on-surface-variant">
                        No past conversations yet.
                      </p>
                    ) : (
                      conversations.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          role="option"
                          aria-selected={c.id === conversationId}
                          onClick={() => selectConversation(c.id)}
                          className={`w-full text-left px-3 py-1.5 text-caption hover:bg-surface-container-low ${
                            c.id === conversationId
                              ? "text-on-surface font-medium"
                              : "text-on-surface-variant"
                          }`}
                        >
                          <span className="block truncate">{c.title}</span>
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        {telegramDrafts.length > 0 && (
          <div className="px-gutter-desktop max-w-3xl mx-auto w-full mt-3">
            <div className="bg-primary/5 border border-primary/20 rounded-lg px-4 py-2 flex items-center justify-between gap-3">
              <p className="text-caption text-on-surface">
                📲 {telegramDrafts.length} Telegram message
                {telegramDrafts.length === 1 ? "" : "s"} waiting
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="text-caption text-primary font-medium hover:underline"
                  onClick={() => {
                    setDraft((cur) =>
                      cur
                        ? `${cur}\n\n${telegramDrafts.map((d) => d.text).join("\n")}`
                        : telegramDrafts.map((d) => d.text).join("\n"),
                    );
                    // S3 audit fix #9: claim drafts when the operator
                    // pulls them into the composer; otherwise the
                    // banner reappears on every refresh forever.
                    void claimTelegramDraftIds(telegramDrafts.map((d) => d.id));
                  }}
                >
                  Show
                </button>
                <button
                  type="button"
                  className="text-caption text-on-surface-variant hover:underline"
                  onClick={() =>
                    void claimTelegramDraftIds(telegramDrafts.map((d) => d.id))
                  }
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-gutter-desktop py-vertical-gap">
          <div className="max-w-3xl mx-auto space-y-6 pb-32">
            {showEmpty ? (
              <div className="flex flex-col items-center justify-center py-24 text-center gap-3">
                <MessageCircle
                  className="h-16 w-16 text-on-surface-variant/30"
                  strokeWidth={1.5}
                />
                <h3 className="text-heading font-semibold text-on-surface">
                  Talk to Self Jr
                </h3>
                <p className="text-caption text-on-surface-variant max-w-md">
                  Project-context-aware. Ask about progress, redirect the
                  active CLI, or queue work for the next session.
                </p>
                <div className="flex flex-wrap gap-2 justify-center mt-4">
                  {EXAMPLE_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setDraft(prompt)}
                      className="px-3 py-1.5 bg-surface-container-low hover:bg-surface-container text-caption text-on-surface-variant rounded-full transition-colors"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((m) => (
                  <ChatMessage key={m.id} message={m} />
                ))}
                {sending && (
                  <div className="flex items-center gap-2 text-caption text-on-surface-variant">
                    <Loader2
                      className="h-4 w-4 animate-spin"
                      strokeWidth={2}
                    />
                    Self Jr is thinking…
                  </div>
                )}
                {notice && (
                  <div className="flex items-start gap-2 bg-surface-container-low border border-outline-variant/30 rounded-lg px-3 py-2 text-caption text-on-surface-variant">
                    <AlertTriangle
                      className="h-4 w-4 shrink-0 mt-0.5"
                      strokeWidth={1.75}
                    />
                    <span>{notice}</span>
                  </div>
                )}
                <div ref={feedEndRef} />
              </>
            )}
          </div>
        </div>

        <div className="sticky bottom-0 bg-background border-t border-outline-variant/30 px-gutter-desktop py-4">
          <div className="max-w-3xl mx-auto bg-surface rounded-xl shadow-md border border-outline-variant/30 overflow-hidden">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void onSend();
                }
              }}
              placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
              className="w-full bg-transparent border-none focus:ring-0 outline-none text-body placeholder:text-on-surface-variant/60 resize-none min-h-[44px] max-h-40 px-4 py-3"
              rows={1}
              aria-label="Message"
            />
            <div className="flex items-center justify-between border-t border-outline-variant/20 px-3 py-2 flex-wrap gap-2">
              <div className="flex items-center gap-1 flex-wrap">
                <button
                  type="button"
                  disabled
                  title="File attachments — coming soon"
                  className="p-1.5 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Attach file (coming soon)"
                >
                  <Paperclip
                    className="h-4 w-4 text-on-surface-variant"
                    strokeWidth={1.75}
                  />
                </button>
                <span className="h-4 w-px bg-outline-variant mx-1" />
                {SLASH_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() =>
                      setDraft((d) => d + (d ? " " : "") + chip + " ")
                    }
                    className="px-2 py-1 text-[11px] font-mono text-on-surface-variant hover:bg-surface-container-low rounded transition-colors"
                  >
                    {chip}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => void onSend()}
                disabled={!draft.trim() || sending}
                aria-label="Send message"
                className="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center disabled:opacity-40 hover:bg-primary-container transition-colors"
              >
                <ArrowRight className="h-4 w-4" strokeWidth={2} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
