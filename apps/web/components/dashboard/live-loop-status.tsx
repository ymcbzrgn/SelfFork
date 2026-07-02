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
      <div className="bg-surface rounded-xl border border-outline-variant/10 p-card-padding flex items-center justify-between gap-4">
        <p className="text-body text-on-surface-variant flex items-center gap-2 min-w-0">
          <span className="w-2 h-2 rounded-full bg-on-surface-variant/40 shrink-0" />
          <span className="truncate">Idle — waiting for a task.</span>
        </p>
        <Link
          href="/talk"
          className="text-caption font-bold text-primary hover:underline whitespace-nowrap"
        >
          Start something →
        </Link>
      </div>
    );
  }

  return (
    <div className="bg-surface rounded-xl border border-outline-variant/10 shadow-sm p-card-padding">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <p className="text-body text-on-surface flex items-center gap-2 min-w-0">
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0" />
          <span className="truncate">
            <span className="text-on-surface-variant">Working on </span>
            {loop.workspace}
            <span className="text-on-surface-variant"> — “{loop.thought}”</span>
          </span>
        </p>
        <Link
          href={`/workspaces/${loop.workspaceSlug}`}
          className="text-caption font-bold text-primary hover:underline whitespace-nowrap"
        >
          Open workspace →
        </Link>
      </div>
    </div>
  );
}
