import {
  Activity,
  AlertTriangle,
  Archive,
  ArchiveRestore,
  CheckCircle2,
  HelpCircle,
  MessageCircle,
  PauseCircle,
  Play,
  PlayCircle,
  Send,
  ShieldCheck,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import type { ActivityKind, ActivityRow } from "@/lib/api";

// One icon per activity kind (S8 — the Letta-style discriminated feed). Q/A
// pairs read as a pair via distinct icons (❓ question / ✅ answer) when they
// land adjacently — they share a correlation_id so the backend keeps them
// next to each other in the ts-DESC order.
const KIND_ICON: Record<ActivityKind, LucideIcon> = {
  session_started: Play,
  session_ended: CheckCircle2,
  tool_call: Wrench,
  "tool.structured_question": HelpCircle,
  "tool.structured_answer": CheckCircle2,
  heartbeat_tick: Activity,
  destructive_confirm_requested: AlertTriangle,
  destructive_confirm_resolved: ShieldCheck,
  telegram_inbound: MessageCircle,
  telegram_outbound: Send,
  project_archived: Archive,
  project_unarchived: ArchiveRestore,
  project_paused: PauseCircle,
  project_resumed: PlayCircle,
};

const SEVERITY_CLASS: Record<ActivityRow["severity"], string> = {
  info: "text-on-surface-variant group-hover:text-primary",
  warn: "text-amber-600",
  error: "text-error",
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function ActivityFeedItem({ row }: { row: ActivityRow }) {
  const Icon = KIND_ICON[row.event_kind] ?? Wrench;
  return (
    <tr className="hover:bg-surface-container-low transition-colors group">
      <td className="py-4 pl-6 w-10 align-top">
        <Icon
          className={`w-5 h-5 transition-colors ${SEVERITY_CLASS[row.severity]}`}
          strokeWidth={1.75}
        />
      </td>
      <td className="py-4 font-mono text-[11px] tabular-nums text-on-surface-variant w-[80px] align-top">
        {formatTime(row.ts)}
      </td>
      <td className="py-4 align-top">
        {row.project_slug ? (
          <span className="bg-surface-variant px-2 py-0.5 rounded text-[10px] font-bold uppercase text-on-surface-variant">
            {row.project_slug}
          </span>
        ) : (
          <span className="text-[10px] text-on-surface-variant/40">—</span>
        )}
      </td>
      <td className="py-4 pr-6 text-caption text-on-surface">
        <span>{row.summary}</span>
        {row.intent && (
          <span className="mt-0.5 block text-[11px] italic text-on-surface-variant/70">
            {row.intent}
          </span>
        )}
      </td>
    </tr>
  );
}
