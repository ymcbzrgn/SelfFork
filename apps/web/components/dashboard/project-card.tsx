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
      className="bg-surface p-4 rounded-xl shadow-sm border border-outline-variant/10 hover:-translate-y-1 transition-transform cursor-pointer relative group block"
    >
      <div className="flex justify-between items-start mb-4">
        <span
          className={`${meta.classes} text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-tight`}
        >
          {meta.label}
        </span>
        <ArrowUpRight
          className="w-5 h-5 text-on-surface-variant group-hover:text-primary"
          strokeWidth={1.75}
        />
      </div>
      <h3 className="font-display text-body font-bold text-on-surface">{name}</h3>
      <p className="text-caption text-on-surface-variant">{progress}</p>
    </Link>
  );
}

export function NewProjectCard() {
  return (
    <Link
      href="/talk?intent=new-workspace"
      className="border-2 border-dashed border-outline-variant/50 p-4 rounded-xl flex flex-col items-center justify-center gap-2 hover:bg-surface-container-low transition-colors cursor-pointer group min-h-[110px]"
    >
      <PlusCircle
        className="w-8 h-8 text-primary group-hover:scale-110 transition-transform"
        strokeWidth={1.75}
      />
      <span className="text-caption font-bold text-on-surface-variant">New workspace</span>
    </Link>
  );
}
