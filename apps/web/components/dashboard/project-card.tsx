import Link from "next/link";
import { ArrowUpRight, PlusCircle } from "lucide-react";

export type ProjectStatus = "shipping" | "sleeping" | "pending" | "errored";

const STATUS_META: Record<ProjectStatus, { label: string; classes: string }> = {
  shipping: { label: "Shipping", classes: "bg-green-50 text-green-700" },
  sleeping: { label: "Sleeping", classes: "bg-amber-50 text-amber-700" },
  pending: { label: "Pending Approval", classes: "bg-amber-50 text-amber-700" },
  errored: { label: "Errored", classes: "bg-red-50 text-red-700" },
};

export interface ProjectCardData {
  slug: string;
  name: string;
  status: ProjectStatus;
  progress: string; // "12/24 tasks" or "Awaiting operator"
}

export function ProjectCard({ slug, name, status, progress }: ProjectCardData) {
  const meta = STATUS_META[status];
  return (
    <Link
      href={`/workspaces/${slug}`}
      className="group flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-container-low transition-colors"
    >
      <div className="min-w-0">
        <h3 className="font-display text-body text-on-surface truncate">{name}</h3>
        <p className="text-caption text-on-surface-variant">{progress}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span
          className={`${meta.classes} text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-tight`}
        >
          {meta.label}
        </span>
        <ArrowUpRight
          className="w-4 h-4 text-on-surface-variant/50 group-hover:text-primary transition-colors"
          strokeWidth={1.75}
        />
      </div>
    </Link>
  );
}

export function NewProjectCard() {
  return (
    <Link
      href="/talk?intent=new-workspace"
      className="group flex items-center gap-2 px-4 py-3 text-on-surface-variant hover:bg-surface-container-low transition-colors"
    >
      <PlusCircle
        className="w-4 h-4 text-primary shrink-0"
        strokeWidth={1.75}
      />
      <span className="text-caption font-medium">New workspace</span>
    </Link>
  );
}
