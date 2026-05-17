"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  History,
  MessageCircle,
  Paperclip,
  Plus,
} from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { listProjects, type ProjectResponse } from "@/lib/api";

interface ChatMessage {
  id: string;
  role: "operator" | "self-jr" | "system";
  workspace?: string;
  cli?: string;
  text: string;
  ts: string;
  actions?: Array<{ label: string; href: string }>;
}

const SLASH_CHIPS = ["/cli", "/workspace", "/pause", "/note", "/finetune"];

const PROVIDER_PILL: Record<string, string> = {
  claude: "bg-amber-50 text-amber-700",
  codex: "bg-green-50 text-green-700",
  gemini: "bg-blue-50 text-blue-700",
  minimax: "bg-violet-50 text-violet-700",
  glm: "bg-red-50 text-red-700",
  system: "bg-surface-container text-on-surface-variant",
};

export default function TalkPage() {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [contextSlug, setContextSlug] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [messages] = useState<ChatMessage[]>([]); // backend wire: GET /api/talk + WS
  const [openContextMenu, setOpenContextMenu] = useState(false);

  useEffect(() => {
    listProjects()
      .then((p) => {
        setProjects(p);
        if (p[0]) setContextSlug(p[0].slug);
      })
      .catch(() => {
        /* graceful */
      });
  }, []);

  const contextLabel = useMemo(() => {
    if (!contextSlug) return "All projects";
    const p = projects.find((x) => x.slug === contextSlug);
    return p?.name ?? contextSlug;
  }, [contextSlug, projects]);

  const onSend = () => {
    if (!draft.trim()) return;
    // TODO: backend wire — POST /api/talk/send { workspace: contextSlug, text: draft }
    setDraft("");
  };

  return (
    <AppShell title="Talk">
      <div className="flex flex-col min-h-[calc(100vh-theme(spacing.topbar-height))] bg-background relative">
        <header className="px-gutter-desktop pt-vertical-gap max-w-3xl mx-auto w-full">
          <div className="flex items-start justify-between flex-wrap gap-3">
            <div>
              <h1 className="font-display text-display text-on-surface">Talk</h1>
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
                className="px-3 py-1.5 border border-outline-variant text-caption font-medium rounded-lg hover:bg-surface-container-low flex items-center gap-1"
              >
                <Plus className="h-4 w-4" strokeWidth={1.75} />
                New chat
              </button>
              <button
                type="button"
                className="px-3 py-1.5 text-on-surface-variant hover:bg-surface-container-low text-caption font-medium rounded-lg flex items-center gap-1"
              >
                <History className="h-4 w-4" strokeWidth={1.75} />
                History
              </button>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-gutter-desktop py-vertical-gap">
          <div className="max-w-3xl mx-auto space-y-6 pb-32">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-24 text-center gap-3">
                <MessageCircle
                  className="h-16 w-16 text-on-surface-variant/30"
                  strokeWidth={1.5}
                />
                <h3 className="text-heading font-semibold text-on-surface">
                  Talk to Self Jr
                </h3>
                <p className="text-caption text-on-surface-variant max-w-md">
                  Project-context-aware. Ask about progress, redirect the active
                  CLI, or queue work for the next session.
                </p>
                <div className="flex flex-wrap gap-2 justify-center mt-4">
                  {[
                    "What did Self Jr ship today?",
                    "Switch ProjectX to Codex",
                    "Pause everything for an hour",
                  ].map((prompt) => (
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
              messages.map((m) => {
                const isOp = m.role === "operator";
                return (
                  <div
                    key={m.id}
                    className={`flex ${isOp ? "justify-end" : "justify-start"}`}
                  >
                    <div className={isOp ? "max-w-md" : "max-w-2xl"}>
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            isOp ? "bg-primary" : "bg-success"
                          }`}
                        />
                        <span className="text-caption font-semibold text-on-surface">
                          {m.role === "operator" ? "operator" : "Self Jr"}
                        </span>
                        <span className="text-[11px] text-on-surface-variant tabular-nums">
                          · {m.ts}
                        </span>
                        {m.workspace && (
                          <span className="bg-surface-variant text-on-surface-variant px-2 py-0.5 rounded text-[10px] font-bold uppercase">
                            {m.workspace}
                          </span>
                        )}
                        {m.cli && (
                          <span
                            className={`${
                              PROVIDER_PILL[m.cli] ?? PROVIDER_PILL.system
                            } px-2 py-0.5 rounded text-[10px] font-bold uppercase`}
                          >
                            {m.cli}
                          </span>
                        )}
                      </div>
                      <div
                        className={`${
                          isOp
                            ? "bg-surface-container-low border border-outline-variant/30"
                            : "bg-surface border border-outline-variant/20 shadow-sm"
                        } p-4 rounded-xl text-body text-on-surface whitespace-pre-wrap`}
                      >
                        {m.text}
                      </div>
                      {m.actions && m.actions.length > 0 && (
                        <div className="flex gap-2 mt-2">
                          {m.actions.map((a) => (
                            <a
                              key={a.label}
                              href={a.href}
                              className="text-caption text-primary hover:underline font-medium"
                            >
                              {a.label} →
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
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
                  onSend();
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
                  className="p-1.5 hover:bg-surface-container-low rounded transition-colors"
                  aria-label="Attach file"
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
                onClick={onSend}
                disabled={!draft.trim()}
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
