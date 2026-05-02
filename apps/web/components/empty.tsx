/**
 * shadcn-style ``Empty`` composition.
 *
 * Shape: ``<Empty><EmptyHeader><EmptyMedia /><EmptyTitle /><EmptyDescription /></EmptyHeader><EmptyContent /></Empty>``.
 * Mirrors the official shadcn Empty pattern (October 2025 release)
 * so existing copy-paste examples translate directly.
 *
 * No-decoration default — ``Empty.Compact`` adds dashed-border framing
 * for use *inside* a column where the empty state should still look
 * like a slot rather than a paragraph.
 */
import { cn } from "@/lib/utils";

export function Empty({
  children,
  className,
  variant = "default",
}: {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "compact";
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center text-center",
        variant === "default" && "px-4 py-12",
        variant === "compact" &&
          "rounded-md border border-dashed border-border/60 px-3 py-6",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function EmptyHeader({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("space-y-2", className)}>{children}</div>;
}

export function EmptyMedia({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      aria-hidden
      className={cn(
        "mx-auto grid h-10 w-10 place-items-center rounded-full bg-muted text-muted-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function EmptyTitle({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <h3 className={cn("text-sm font-medium tracking-tight", className)}>
      {children}
    </h3>
  );
}

export function EmptyDescription({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p className={cn("text-xs text-muted-foreground", className)}>{children}</p>
  );
}

export function EmptyContent({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("mt-3 flex justify-center", className)}>{children}</div>;
}
