/**
 * ChatMessage — one operator ↔ Self Jr bubble in the Talk feed (S1).
 *
 * DESIGN.md §6.3: avatar dot + role label + timestamp; Self Jr bubbles
 * may carry a workspace pill and a colour-coded CLI pill plus footer
 * action links. Operator bubbles align right, Self Jr bubbles left.
 */

export interface ChatMessageAction {
  label: string;
  href: string;
}

export interface ChatMessageView {
  id: string;
  role: "operator" | "self_jr";
  text: string;
  ts: string;
  workspace?: string;
  cli?: string;
  actions?: ChatMessageAction[];
}

const PROVIDER_PILL: Record<string, string> = {
  claude: "bg-amber-50 text-amber-700",
  codex: "bg-green-50 text-green-700",
  gemini: "bg-blue-50 text-blue-700",
  minimax: "bg-violet-50 text-violet-700",
  glm: "bg-red-50 text-red-700",
};

const PROVIDER_PILL_FALLBACK = "bg-surface-container text-on-surface-variant";

export function ChatMessage({ message }: { message: ChatMessageView }) {
  const isOperator = message.role === "operator";
  return (
    <div className={`flex ${isOperator ? "justify-end" : "justify-start"}`}>
      <div className={isOperator ? "max-w-md" : "max-w-2xl"}>
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isOperator ? "bg-primary" : "bg-success"
            }`}
          />
          <span className="text-caption font-semibold text-on-surface">
            {isOperator ? "operator" : "Self Jr"}
          </span>
          <span className="text-[11px] text-on-surface-variant tabular-nums">
            · {message.ts}
          </span>
          {message.workspace && (
            <span className="bg-surface-variant text-on-surface-variant px-2 py-0.5 rounded text-[10px] font-bold uppercase">
              {message.workspace}
            </span>
          )}
          {message.cli && (
            <span
              className={`${
                PROVIDER_PILL[message.cli] ?? PROVIDER_PILL_FALLBACK
              } px-2 py-0.5 rounded text-[10px] font-bold uppercase`}
            >
              {message.cli}
            </span>
          )}
        </div>
        <div
          className={`${
            isOperator
              ? "bg-surface-container-low border border-outline-variant/30"
              : "bg-surface border border-outline-variant/20 shadow-sm"
          } p-4 rounded-xl text-body text-on-surface whitespace-pre-wrap`}
        >
          {message.text}
        </div>
        {message.actions && message.actions.length > 0 && (
          <div className="flex gap-2 mt-2">
            {message.actions.map((a) => (
              <a
                key={a.label}
                href={a.href}
                className="text-caption text-primary hover:underline font-medium"
              >
                {a.label} →
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
