/**
 * Filter chips — Run tab — Order 7.
 *
 * Tiny native ``<select>`` chips for the three categorical filters
 * (tool / cli / category) plus a free-text search input. State lives
 * in the cockpit Zustand store so the AuditStream / TraceTree /
 * Waterfall can react without prop drilling.
 */
"use client";

import { useCockpitStore } from "@/lib/store";

const TOOLS = [
  "rotate_to",
  "sleep_until",
  "notify_telegram",
  "compact_context",
  "mark_done",
  "quota_snapshot",
  "available_clis",
  "session_state",
  "cancel_pending",
  "mind_recall",
  "mind_note_add",
];
const CLIS = [
  "claude-code",
  "codex",
  "gemini-cli",
  "opencode",
  "minimax-cli",
  "zai",
];
const CATEGORIES = [
  "agent.invoke",
  "agent.output",
  "agent.done",
  "agent.rate_limited",
  "tool.call",
  "tool.result",
  "selffork_jr.reply",
  "mind.note.write",
  "mind.recall.query",
  "session.state",
  "error",
];

export function FilterChips() {
  const tool = useCockpitStore((s) => s.runFilterTool);
  const cli = useCockpitStore((s) => s.runFilterCli);
  const category = useCockpitStore((s) => s.runFilterCategory);
  const query = useCockpitStore((s) => s.runSearchQuery);
  const setFilter = useCockpitStore((s) => s.setRunFilter);
  const setQuery = useCockpitStore((s) => s.setRunSearchQuery);

  return (
    <div
      className="flex flex-wrap items-center gap-2 text-xs"
      data-testid="run-filter-chips"
    >
      <FilterSelect
        label="Tool"
        value={tool}
        options={TOOLS}
        onChange={(v) => setFilter("tool", v)}
      />
      <FilterSelect
        label="CLI"
        value={cli}
        options={CLIS}
        onChange={(v) => setFilter("cli", v)}
      />
      <FilterSelect
        label="Category"
        value={category}
        options={CATEGORIES}
        onChange={(v) => setFilter("category", v)}
      />
      <input
        type="search"
        placeholder="Search events…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="rounded-md border border-border bg-card px-2 py-1 font-mono text-[11px]"
      />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | null;
  options: string[];
  onChange: (v: string | null) => void;
}) {
  return (
    <label className="flex items-center gap-1">
      <span className="text-muted-foreground">{label}</span>
      <select
        aria-label={label}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="rounded-md border border-border bg-card px-2 py-1 font-mono text-[11px]"
      >
        <option value="">all</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}
