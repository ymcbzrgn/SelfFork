import Link from "next/link";

export interface LiveLoop {
  workspace: string;
  workspaceSlug: string;
  cli: string;
  turn: number;
  durationLabel: string; // "12m 47s"
  thought: string;
}

export function LiveLoopStatus({ loop }: { loop: LiveLoop | null }) {
  if (!loop) {
    return (
      <div className="bg-surface border-l-[6px] border-outline-variant/30 rounded-xl shadow-sm p-card-padding flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <span className="text-caption uppercase tracking-wider font-bold text-on-surface-variant">
            Idle
          </span>
          <span className="text-body text-on-surface">Self Jr is waiting for a task.</span>
        </div>
        <Link
          href="/talk"
          className="text-caption font-bold text-primary hover:underline"
        >
          Start something →
        </Link>
      </div>
    );
  }

  return (
    <div className="relative bg-surface border-l-[6px] border-primary-container rounded-xl shadow-sm overflow-hidden">
      <div className="p-card-padding">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="bg-error/10 text-error px-2 py-0.5 rounded flex items-center gap-1.5 font-bold text-[10px] tracking-wider uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-error animate-pulse-red" />
              Live Loop
            </div>
            <span className="text-caption font-mono text-on-surface-variant">
              {loop.workspace} · {loop.cli} CLI · turn {loop.turn} · {loop.durationLabel}
            </span>
          </div>
          <Link
            href={`/workspaces/${loop.workspaceSlug}`}
            className="bg-primary text-white text-caption font-bold px-4 py-2 rounded-lg hover:bg-primary-container transition-colors shadow-sm whitespace-nowrap"
          >
            Open Workspace →
          </Link>
        </div>
        <p className="text-heading text-on-surface font-body leading-relaxed max-w-2xl italic">
          “{loop.thought}”
        </p>
      </div>
    </div>
  );
}
