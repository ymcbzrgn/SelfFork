import { ChevronDown, Pause, Terminal } from "lucide-react";

export interface CLIOutputChunk {
  id: string;
  kind: "stdout" | "stderr" | "system" | "jr-prompt" | "info";
  text: string;
}

export interface Screenshot {
  id: string;
  at: string; // "10:25"
  thumbnailUrl?: string;
  previewUrl?: string;
  active?: boolean;
  visionTier?: 1 | 2 | 3;
}

export interface JrThought {
  id: string;
  summary: string;
  raw?: string;
}

export interface LiveRunTheaterState {
  active: boolean;
  cli: string;
  turn: number;
  durationLabel: string;
  output: CLIOutputChunk[];
  screenshots: Screenshot[];
  thoughts: JrThought[];
  nextPrompt?: string;
}

function CLIOutputPane({ output }: { output: CLIOutputChunk[] }) {
  return (
    <div className="w-full md:w-[40%] flex flex-col" style={{ backgroundColor: "#1A1A1F" }}>
      <div className="px-4 py-2 bg-white/5 border-b border-white/10 flex items-center justify-between">
        <span className="text-[10px] font-mono text-white/40 uppercase tracking-wider">
          CLI Output
        </span>
        <Terminal className="h-4 w-4 text-white/30" strokeWidth={1.75} />
      </div>
      <div className="flex-1 p-4 font-mono text-xs leading-relaxed overflow-y-auto">
        {output.length === 0 ? (
          <p className="text-white/40 italic">No CLI session active.</p>
        ) : (
          output.map((c) => {
            const cls =
              c.kind === "stderr"
                ? "text-red-400"
                : c.kind === "system"
                  ? "text-cyan-300"
                  : c.kind === "jr-prompt"
                    ? "text-primary-fixed-dim italic"
                    : c.kind === "info"
                      ? "text-white/40"
                      : "text-white/80";
            return (
              <div key={c.id} className={`${cls} mb-1`}>
                {c.text}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function ScreenshotTimeline({ screenshots }: { screenshots: Screenshot[] }) {
  const active = screenshots.find((s) => s.active) ?? screenshots[screenshots.length - 1];
  return (
    <div className="w-full md:w-[30%] flex flex-col border-l border-outline-variant/40 bg-surface">
      <div className="px-4 py-2 bg-surface-container-low border-b border-outline-variant/40 flex items-center justify-between">
        <span className="text-[10px] font-mono text-on-surface-variant uppercase tracking-wider">
          Screenshots
        </span>
        <span className="text-[10px] text-on-surface-variant">
          {screenshots.length}
        </span>
      </div>
      {screenshots.length === 0 ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-caption text-on-surface-variant/60 italic text-center">
            No screenshots yet.
            <br />
            Self Jr will capture vision frames as the session runs.
          </p>
        </div>
      ) : (
        <>
          <div className="flex gap-1 overflow-x-auto p-2 border-b border-outline-variant/30">
            {screenshots.map((s) => (
              <div
                key={s.id}
                className={`flex-shrink-0 w-[80px] h-[60px] rounded border ${
                  s.active
                    ? "ring-2 ring-primary border-transparent"
                    : "border-outline-variant/40"
                } overflow-hidden bg-surface-container-low`}
              >
                {s.thumbnailUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={s.thumbnailUrl}
                    alt={`Screenshot at ${s.at}`}
                    className="w-full h-full object-cover"
                  />
                ) : null}
              </div>
            ))}
          </div>
          <div className="flex-1 p-3 flex flex-col items-center gap-2">
            <div className="w-full aspect-video bg-surface-container-low rounded border border-outline-variant/30 overflow-hidden">
              {active?.previewUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={active.previewUrl}
                  alt={`Active preview at ${active.at}`}
                  className="w-full h-full object-cover"
                />
              ) : null}
            </div>
            <p className="text-[10px] font-mono text-on-surface-variant tabular-nums">
              {active?.at} · Vision tier: tier-{active?.visionTier ?? 1}
            </p>
          </div>
        </>
      )}
    </div>
  );
}

function JrThoughtBubble({
  thoughts,
  nextPrompt,
}: {
  thoughts: JrThought[];
  nextPrompt?: string;
}) {
  return (
    <div className="w-full md:w-[30%] flex flex-col border-l border-outline-variant/40 bg-surface-container-low/30">
      <div className="px-4 py-2 border-b border-outline-variant/40 flex items-center justify-between">
        <span className="text-[10px] font-mono text-on-surface-variant uppercase tracking-wider">
          Self Jr's thoughts
        </span>
      </div>
      <div className="flex-1 p-4 overflow-y-auto space-y-3">
        {thoughts.length === 0 ? (
          <p className="text-caption text-on-surface-variant/60 italic">
            Self Jr is observing — no thoughts surfaced yet.
          </p>
        ) : (
          thoughts.map((t) => (
            <p key={t.id} className="text-caption italic text-on-surface-variant leading-relaxed">
              <span className="text-primary mr-1">▸</span>
              {t.summary}
            </p>
          ))
        )}
        {nextPrompt && (
          <div className="border-t border-outline-variant/40 pt-3 mt-3">
            <p className="text-[10px] uppercase tracking-wider text-on-surface-variant mb-1">
              Next prompt
            </p>
            <p className="text-caption italic text-on-surface">{nextPrompt}</p>
          </div>
        )}
      </div>
      <div className="border-t border-outline-variant/40 p-2 flex justify-end">
        <button
          type="button"
          className="text-[10px] text-on-surface-variant hover:text-on-surface font-medium px-2 py-1 rounded transition-colors"
        >
          show raw ▾
        </button>
      </div>
    </div>
  );
}

export interface LiveRunTheaterProps {
  state: LiveRunTheaterState | null;
  onPause?: () => void;
  onSwitchCli?: () => void;
  onOpenTranscript?: () => void;
}

export function LiveRunTheater({
  state,
  onPause,
  onSwitchCli,
  onOpenTranscript,
}: LiveRunTheaterProps) {
  if (!state || !state.active) {
    return (
      <section className="bg-surface-container-lowest rounded-2xl shadow-md overflow-hidden border border-surface-variant">
        <div className="bg-surface-container-high px-6 py-4 flex items-center justify-between border-b border-outline-variant">
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-on-surface-variant/50" />
            <span className="font-bold text-caption tracking-widest text-on-surface-variant">
              IDLE
            </span>
          </div>
        </div>
        <div className="p-16 flex flex-col items-center justify-center gap-3 text-center">
          <Terminal className="h-12 w-12 text-on-surface-variant/40" strokeWidth={1.5} />
          <h4 className="text-heading font-semibold text-on-surface">No live session</h4>
          <p className="text-caption text-on-surface-variant max-w-md">
            Self Jr isn't running a CLI for this workspace yet. Start a new task
            in the kanban above, or send a prompt from Talk.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="bg-surface-container-lowest rounded-2xl shadow-md overflow-hidden border border-surface-variant">
      <div className="bg-surface-container-high px-6 py-4 flex items-center justify-between border-b border-outline-variant flex-wrap gap-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-error animate-pulse-red" />
            <span className="font-bold text-caption tracking-widest text-on-surface">LIVE</span>
          </div>
          <div className="h-4 w-px bg-outline-variant" />
          <span className="font-mono text-[11px] text-on-surface-variant">
            {state.cli} · turn {state.turn} · {state.durationLabel}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onPause}
            className="bg-surface-container-lowest px-3 py-1.5 rounded-lg text-[11px] font-semibold shadow-sm hover:bg-surface-container flex items-center gap-1.5 border border-outline-variant"
          >
            <Pause className="h-3.5 w-3.5" strokeWidth={1.75} />
            Pause
          </button>
          <button
            type="button"
            onClick={onSwitchCli}
            className="bg-surface-container-lowest px-3 py-1.5 rounded-lg text-[11px] font-semibold shadow-sm hover:bg-surface-container flex items-center gap-1.5 border border-outline-variant"
          >
            Switch CLI
            <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
          </button>
          <button
            type="button"
            onClick={onOpenTranscript}
            className="text-primary px-3 py-1.5 rounded-lg text-[11px] font-bold hover:bg-primary/5 transition-colors"
          >
            Open transcript
          </button>
        </div>
      </div>
      <div className="flex flex-col md:flex-row min-h-[480px]">
        <CLIOutputPane output={state.output} />
        <ScreenshotTimeline screenshots={state.screenshots} />
        <JrThoughtBubble thoughts={state.thoughts} nextPrompt={state.nextPrompt} />
      </div>
    </section>
  );
}
