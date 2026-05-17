import {
  CheckCircle2,
  AlertTriangle,
  Bell,
  Cog,
  CloudUpload,
  GitCommit,
  MessageCircle,
  StickyNote,
  Wrench,
  type LucideIcon,
} from "lucide-react";

const ICON_MAP: Record<string, LucideIcon> = {
  commit: GitCommit,
  construction: Wrench,
  cog: Cog,
  cloud_upload: CloudUpload,
  forum: MessageCircle,
  task_alt: CheckCircle2,
  note: StickyNote,
  warning: AlertTriangle,
  bell: Bell,
};

export interface ActivityRow {
  id: string;
  icon: keyof typeof ICON_MAP;
  time: string; // "14:22:01" or "5m ago"
  workspace: string; // pill label
  message: string;
}

export function ActivityFeedItem({ row }: { row: ActivityRow }) {
  const Icon = ICON_MAP[row.icon] ?? GitCommit;
  return (
    <tr className="hover:bg-surface-container-low transition-colors group">
      <td className="py-4 pl-6 w-10">
        <Icon
          className="w-5 h-5 text-on-surface-variant group-hover:text-primary transition-colors"
          strokeWidth={1.75}
        />
      </td>
      <td className="py-4 font-mono text-[11px] tabular-nums text-on-surface-variant w-[80px]">
        {row.time}
      </td>
      <td className="py-4">
        <span className="bg-surface-variant px-2 py-0.5 rounded text-[10px] font-bold uppercase text-on-surface-variant">
          {row.workspace}
        </span>
      </td>
      <td className="py-4 pr-6 text-caption text-on-surface">{row.message}</td>
    </tr>
  );
}
