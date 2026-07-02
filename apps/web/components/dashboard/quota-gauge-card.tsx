import Link from "next/link";

const PROVIDER_META: Record<
  string,
  { label: string; textClass: string; barClass: string }
> = {
  claude: { label: "claude", textClass: "text-amber-600", barClass: "bg-amber-500" },
  "claude-code": { label: "claude", textClass: "text-amber-600", barClass: "bg-amber-500" },
  codex: { label: "codex", textClass: "text-green-600", barClass: "bg-green-500" },
  gemini: { label: "gemini", textClass: "text-blue-600", barClass: "bg-blue-500" },
  "gemini-cli": { label: "gemini", textClass: "text-blue-600", barClass: "bg-blue-500" },
  minimax: { label: "minimax", textClass: "text-violet-600", barClass: "bg-violet-500" },
  glm: { label: "glm", textClass: "text-red-600", barClass: "bg-red-500" },
  opencode: { label: "opencode", textClass: "text-on-surface-variant", barClass: "bg-on-surface-variant" },
};

export interface QuotaCard {
  provider: string;
  quota?: number; // 0–100; undefined means unknown
  resetIn?: string; // human-readable "4h 12m left" / "resets in 5h"
  signedIn: boolean;
}

export function QuotaGaugeCard({ provider, quota, resetIn, signedIn }: QuotaCard) {
  const meta = PROVIDER_META[provider] ?? {
    label: provider,
    textClass: "text-on-surface-variant",
    barClass: "bg-on-surface-variant",
  };

  if (!signedIn) {
    return (
      <div className="w-[160px] h-[120px] bg-surface-container-low/50 rounded-lg p-4 border border-dashed border-outline-variant/40 flex flex-col justify-between opacity-70">
        <span className="text-caption font-bold text-on-surface-variant">{meta.label}</span>
        <Link
          href="/connections"
          className="text-caption font-bold text-primary flex items-center justify-center gap-1 hover:underline"
        >
          Sign in →
        </Link>
      </div>
    );
  }

  const pct = quota ?? 0;
  const low = pct < 30;
  const barColor = low ? "bg-amber-500" : "bg-on-surface-variant/60";
  const borderClass = low
    ? "border-2 border-amber-400/50"
    : "border border-outline-variant/10";

  return (
    <div
      className={`w-[160px] h-[120px] bg-surface rounded-lg p-4 shadow-sm ${borderClass} hover:shadow-md transition-shadow`}
    >
      <div className="flex justify-between items-start mb-2">
        <span className="text-caption font-medium text-on-surface-variant">{meta.label}</span>
        <span className="text-caption tabular-nums font-semibold text-on-surface">
          {quota === undefined ? "—" : `${pct}%`}
        </span>
      </div>
      <div className="w-full bg-surface-variant h-1.5 rounded-full mb-3">
        <div
          className={`${barColor} h-1.5 rounded-full transition-all`}
          style={{ width: `${pct}%` }}
          aria-label={`${meta.label} quota ${pct}%`}
        />
      </div>
      <p className="text-[11px] text-on-surface-variant tabular-nums">{resetIn ?? "—"}</p>
    </div>
  );
}
