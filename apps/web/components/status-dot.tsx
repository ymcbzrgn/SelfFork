/**
 * Vercel Geist-style status dot.
 *
 * Five lifecycle states; the dot pulses (`animate-ping` halo) only
 * while the work is still in flight. Terminal states render a static
 * solid dot — no spinner ever coexists. This is the single contract
 * used in cards, badges, sidebar footer.
 *
 * Color resolution uses semantic Tailwind tokens so dark/light themes
 * and the (future) LCH palette swap stay coherent.
 */
import { cn } from "@/lib/utils";

export type StatusState =
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "killed"
  | "idle";

const COLOR: Record<StatusState, string> = {
  queued: "bg-info",
  running: "bg-info",
  done: "bg-success",
  failed: "bg-destructive",
  killed: "bg-muted-foreground",
  idle: "bg-muted-foreground/60",
};

const TRANSIENT: Record<StatusState, boolean> = {
  queued: true,
  running: true,
  done: false,
  failed: false,
  killed: false,
  idle: false,
};

export function StatusDot({
  state,
  size = "sm",
  className,
  label,
}: {
  state: StatusState;
  size?: "xs" | "sm" | "md";
  className?: string;
  /** Accessible name; passed via aria-label on the wrapper. */
  label?: string;
}) {
  const dim = size === "xs" ? "h-1.5 w-1.5" : size === "md" ? "h-2.5 w-2.5" : "h-2 w-2";
  const transient = TRANSIENT[state];
  const color = COLOR[state];
  return (
    <span
      role="status"
      aria-label={label ?? state}
      className={cn("relative inline-flex items-center justify-center", className)}
    >
      <span className={cn("relative inline-flex rounded-full", dim, color)}>
        {transient && (
          <span
            aria-hidden
            className={cn(
              "absolute inset-0 rounded-full opacity-75 motion-safe:animate-ping",
              color,
            )}
          />
        )}
      </span>
    </span>
  );
}
