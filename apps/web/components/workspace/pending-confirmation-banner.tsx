import { ArrowRight, Bell, AlertTriangle } from "lucide-react";

export interface PendingAction {
  id: string;
  command: string; // e.g. "git push origin main"
  description: string; // e.g. "1 destructive action pending approval"
  timeLeft: string; // e.g. "3h 27m left"
  detailsHref?: string;
}

export interface PendingConfirmationBannerProps {
  pending: PendingAction | null;
  onApprove?: (id: string) => void;
  onCancel?: (id: string) => void;
  onExtend?: (id: string, hours: number) => void;
}

export function PendingConfirmationBanner({
  pending,
  onApprove,
  onCancel,
  onExtend,
}: PendingConfirmationBannerProps) {
  if (!pending) return null;
  return (
    <section
      className="bg-[#FEFCE8] border-l-4 border-yellow-500 p-4 rounded-r-xl flex items-center justify-between shadow-sm flex-wrap gap-3"
      role="alert"
    >
      <div className="flex items-center gap-4">
        <div className="flex -space-x-2">
          <AlertTriangle
            className="h-7 w-7 text-yellow-700 bg-yellow-100 p-1 rounded-full"
            strokeWidth={1.75}
          />
          <Bell
            className="h-7 w-7 text-yellow-700 bg-yellow-100 p-1 rounded-full border-2 border-[#FEFCE8]"
            strokeWidth={1.75}
          />
        </div>
        <div className="flex flex-col">
          <p className="text-on-surface font-medium flex items-center gap-2 flex-wrap">
            {pending.description} —
            <code className="bg-white/60 border border-yellow-200 px-2 py-0.5 rounded font-mono text-caption text-yellow-900">
              {pending.command}
            </code>
          </p>
          <p className="text-yellow-800/80 text-caption font-mono tabular-nums">
            {pending.timeLeft}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onApprove?.(pending.id)}
          className="bg-primary text-white px-5 py-2 rounded-lg font-medium text-caption hover:bg-primary-container transition-colors"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={() => onCancel?.(pending.id)}
          className="text-on-surface-variant hover:bg-black/5 px-4 py-2 rounded-lg font-medium text-caption transition-colors"
        >
          Cancel
        </button>
        {onExtend ? (
          <button
            type="button"
            onClick={() => onExtend(pending.id, 2)}
            className="text-yellow-900 border border-yellow-300 hover:bg-yellow-100 px-3 py-2 rounded-lg font-medium text-caption transition-colors"
            title="Push the soft-confirm window by 2 hours"
          >
            Extend 2h
          </button>
        ) : null}
        {pending.detailsHref ? (
          <a
            href={pending.detailsHref}
            className="text-primary font-medium text-caption flex items-center gap-1 ml-2"
          >
            Details
            <ArrowRight className="h-4 w-4" strokeWidth={1.75} />
          </a>
        ) : null}
      </div>
    </section>
  );
}
