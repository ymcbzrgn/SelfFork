import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title: string;
  detail?: string;
  className?: string;
}

export function ErrorState({ title, detail, className }: ErrorStateProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm",
        className,
      )}
    >
      <p className="font-medium text-destructive">{title}</p>
      {detail ? (
        <p className="mt-1 text-xs text-destructive/80">{detail}</p>
      ) : null}
    </div>
  );
}
