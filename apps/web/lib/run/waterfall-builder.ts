/**
 * Flat audit events → waterfall rows (Order 7).
 *
 * Each row carries ``startMs`` (relative to the first event) and
 * ``durationMs`` (computed from the next event's ts, or 0 for the
 * tail event). Rendered as plain HTML/CSS gantt rows in
 * ``Waterfall.tsx`` — no D3/visx dependency.
 */
import type { AuditEvent } from "@/lib/api";

export interface WaterfallRow {
  id: string;
  category: string;
  label: string;
  startMs: number;
  durationMs: number;
  groupKey: string;
  payload: Record<string, unknown>;
  /**
   * True when ``durationMs`` was clamped from a sleep / rate_limited
   * cooldown (Order 7 audit fix). The renderer can show a break /
   * dashed bar so a 5h sleep doesn't compress every other event into
   * sub-pixel widths. The original duration is in ``rawDurationMs``.
   */
  isClampedSleep: boolean;
  rawDurationMs: number;
}

// 60 seconds — anything longer compresses the whole canvas. Audit
// observation: a single 5 h ``agent.rate_limited → ScheduledResume``
// gap dominated 18 000 000 ms when un-clamped.
const SLEEP_CLAMP_MS = 60_000;
const SLEEP_TRIGGER_CATEGORIES = new Set([
  "agent.rate_limited",
  "agent.auth_required",
]);

export function buildWaterfall(events: AuditEvent[]): WaterfallRow[] {
  if (events.length === 0) return [];
  const sorted = [...events].sort((a, b) => a.ts.localeCompare(b.ts));
  const baseline = Date.parse(sorted[0].ts);
  // Two-pass: compute raw durations first, decide clamps, then derive
  // ``startMs`` from the *clamped* prefix so the canvas stays compact.
  const raw: number[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const next = sorted[i + 1];
    raw.push(
      next !== undefined
        ? Math.max(0, Date.parse(next.ts) - Date.parse(sorted[i].ts))
        : 0,
    );
  }
  const rows: WaterfallRow[] = [];
  let cursor = 0;
  for (let i = 0; i < sorted.length; i++) {
    const ev = sorted[i];
    const rawDuration = raw[i];
    const isClamped =
      SLEEP_TRIGGER_CATEGORIES.has(ev.category) &&
      rawDuration > SLEEP_CLAMP_MS;
    const duration = isClamped ? SLEEP_CLAMP_MS : rawDuration;
    rows.push({
      id: `${ev.category}-${i}`,
      category: ev.category,
      label: labelFor(ev),
      startMs: cursor,
      durationMs: duration,
      groupKey: groupKeyFor(ev),
      payload: ev.payload,
      isClampedSleep: isClamped,
      rawDurationMs: rawDuration,
    });
    cursor += duration;
  }
  // Index 0 always starts at the canvas origin (operator expectation:
  // first event begins at startMs=0). The cursor-derived loop above
  // already establishes this since ``cursor`` starts at 0; this guard
  // pins it explicitly for the reader.
  if (rows.length > 0) rows[0].startMs = 0;
  void baseline; // baseline retained for future absolute-clock display
  return rows;
}

function labelFor(ev: AuditEvent): string {
  const round = ev.payload["round"];
  switch (ev.category) {
    case "agent.invoke":
      return `Round ${formatRound(round)}`;
    case "tool.call":
      return `${ev.payload["tool"] ?? "tool"} (call)`;
    case "tool.result":
      return `${ev.payload["tool"] ?? "tool"} (result)`;
    case "selffork_jr.reply":
      return "Jr reply";
    case "agent.output":
      return `Round ${formatRound(round)} output`;
    case "agent.done":
      return "Done";
    case "session.state":
      return `→ ${ev.payload["to"] ?? "?"}`;
    default:
      return ev.category;
  }
}

function groupKeyFor(ev: AuditEvent): string {
  const round = ev.payload["round"];
  if (typeof round === "number") return `round-${round}`;
  return "session";
}

function formatRound(value: unknown): string {
  if (typeof value === "number") return String(value);
  return "?";
}
