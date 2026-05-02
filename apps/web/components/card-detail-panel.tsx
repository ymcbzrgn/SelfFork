/**
 * Slide-in right pane for opening a kanban card without losing the
 * board context (Asana "Better Boards" rationale: modals make users
 * lose place; slide-in keeps the board visible behind the panel).
 *
 * Tabs: Overview / Logs / Tools / Settings. Logs + Tools are
 * placeholder Empty states for now — they'll wire to the audit
 * event stream and tool call history once the backend exposes
 * per-card filters.
 */
"use client";

import { Activity, Settings, Wrench, FileText, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/empty";
import { RelativeAge } from "@/components/format";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { type KanbanCardResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "overview" | "logs" | "tools" | "settings";

interface CardDetailPanelProps {
  card: KanbanCardResponse | null;
  onClose: () => void;
  onDelete: (cardId: string) => Promise<void> | void;
}

export function CardDetailPanel({ card, onClose, onDelete }: CardDetailPanelProps) {
  const [tab, setTab] = useState<Tab>("overview");
  const open = card !== null;

  // Esc closes; ignore when an editable element has focus inside the panel.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) {
        return;
      }
      e.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Reset to overview each time a different card opens.
  useEffect(() => {
    if (card) setTab("overview");
  }, [card?.id]);

  return (
    <>
      {/* Backdrop — semi-transparent, click closes. */}
      <div
        aria-hidden
        onClick={onClose}
        className={cn(
          "fixed inset-0 z-30 bg-black/30 backdrop-blur-[2px] transition-opacity duration-150",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />
      {/* Slide-in panel. */}
      <aside
        role="complementary"
        aria-label="Card detail"
        className={cn(
          "fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-border bg-card shadow-2xl transition-transform duration-200 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        {card ? (
          <>
            <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div className="flex flex-1 items-center gap-2">
                <StatusPill state={card.column} />
                <span className="font-mono text-[10px] text-muted-foreground">
                  {card.id.slice(-8)}
                </span>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close panel"
                title="Close (esc)"
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </header>

            <div className="border-b border-border px-4 py-3">
              <h2 className="break-words text-base font-semibold leading-snug">
                {card.title}
              </h2>
              <p className="mt-1 text-[11px] text-muted-foreground">
                updated <RelativeAge isoTs={card.updated_at} /> · created{" "}
                <RelativeAge isoTs={card.created_at} />
              </p>
            </div>

            <Tabs current={tab} onChange={setTab} />

            <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
              {tab === "overview" && <OverviewTab card={card} />}
              {tab === "logs" && <LogsTab />}
              {tab === "tools" && <ToolsTab />}
              {tab === "settings" && <SettingsTab card={card} onDelete={onDelete} />}
            </div>
          </>
        ) : null}
      </aside>
    </>
  );
}

const TABS: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Overview", icon: FileText },
  { id: "logs", label: "Logs", icon: Activity },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "settings", label: "Settings", icon: Settings },
];

function Tabs({
  current,
  onChange,
}: {
  current: Tab;
  onChange: (next: Tab) => void;
}) {
  return (
    <nav
      role="tablist"
      aria-label="Card sections"
      className="flex border-b border-border px-2"
    >
      {TABS.map((t) => {
        const Icon = t.icon;
        const active = current === t.id;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={cn(
              "relative inline-flex items-center gap-1.5 px-3 py-2 text-xs transition-colors",
              active
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{t.label}</span>
            {active ? (
              <span
                aria-hidden
                className="absolute inset-x-0 -bottom-px h-px bg-foreground"
              />
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}

function OverviewTab({ card }: { card: KanbanCardResponse }) {
  return (
    <div className="space-y-4">
      <section>
        <h3 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Description
        </h3>
        {card.body ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{card.body}</p>
        ) : (
          <p className="text-sm italic text-muted-foreground">No description.</p>
        )}
      </section>
      <section>
        <h3 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Metadata
        </h3>
        <dl className="space-y-1.5 text-xs">
          <Row label="ID" value={<span className="font-mono">{card.id}</span>} />
          <Row label="Column" value={card.column} />
          <Row
            label="Created"
            value={
              <span title={card.created_at}>
                <RelativeAge isoTs={card.created_at} />
              </span>
            }
          />
          <Row
            label="Updated"
            value={
              <span title={card.updated_at}>
                <RelativeAge isoTs={card.updated_at} />
              </span>
            }
          />
          {card.last_touched_by_session_id ? (
            <Row
              label="Last touched"
              value={
                <span className="font-mono">
                  {card.last_touched_by_session_id.slice(0, 12)}…
                </span>
              }
            />
          ) : null}
          {card.completed_at ? (
            <Row
              label="Completed"
              value={
                <span title={card.completed_at}>
                  <RelativeAge isoTs={card.completed_at} />
                </span>
              }
            />
          ) : null}
        </dl>
      </section>
    </div>
  );
}

function LogsTab() {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia>
          <Activity className="h-5 w-5" />
        </EmptyMedia>
        <EmptyTitle>No logs yet</EmptyTitle>
        <EmptyDescription>
          Audit events that touch this card will surface here once the
          backend filter ships.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

function ToolsTab() {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia>
          <Wrench className="h-5 w-5" />
        </EmptyMedia>
        <EmptyTitle>No tool calls</EmptyTitle>
        <EmptyDescription>
          Jr's <code className="font-mono">kanban_card_*</code> calls
          targeting this card will appear here.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

function SettingsTab({
  card,
  onDelete,
}: {
  card: KanbanCardResponse;
  onDelete: (cardId: string) => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const handleDelete = async () => {
    if (busy) return;
    if (typeof window !== "undefined") {
      if (!window.confirm(`Delete card "${card.title}"? This cannot be undone.`)) {
        return;
      }
    }
    setBusy(true);
    try {
      await onDelete(card.id);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
        <h3 className="mb-1 text-xs font-medium text-destructive">
          Danger zone
        </h3>
        <p className="mb-3 text-[11px] text-muted-foreground">
          Deleting a card removes it from disk; Jr will not see it on its
          next round.
        </p>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          onClick={handleDelete}
          disabled={busy}
        >
          {busy ? "Deleting…" : "Delete card"}
        </Button>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/40 py-1 last:border-b-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right text-foreground">{value}</dd>
    </div>
  );
}
