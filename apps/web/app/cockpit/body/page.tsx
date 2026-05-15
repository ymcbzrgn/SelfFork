/**
 * Cockpit Body view (M5 — ADR-005 §M5-D).
 *
 * Three columns: active sessions (with Stop button), the rolling action
 * stream filtered to ``body.*`` audit categories, and pending permission
 * prompts that need operator approval.
 */
"use client";

import { useCockpitStore, type BodyEvent, type BodySession } from "@/lib/store";

function SessionCard({ session }: { session: BodySession }) {
  const stop = async () => {
    await fetch(`/api/body/sessions/${session.session_id}/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "ui_button" }),
    });
  };
  return (
    <div
      className="border rounded p-3 flex items-center justify-between"
      data-testid={`body-session-${session.session_id}`}
    >
      <div>
        <div className="font-mono text-sm">{session.session_id}</div>
        <div className="text-xs text-zinc-500">
          {session.driver} · started {session.started_at}
        </div>
        <div className="text-xs text-zinc-500">
          last activity {session.last_activity}
        </div>
      </div>
      <button
        type="button"
        disabled={session.killed}
        onClick={stop}
        className="text-sm rounded px-3 py-1 bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
      >
        {session.killed ? "Killed" : "Stop"}
      </button>
    </div>
  );
}

function EventRow({ event }: { event: BodyEvent }) {
  const tierColour = {
    T0: "text-zinc-500",
    T1: "text-blue-700",
    T2: "text-amber-700",
    T3: "text-red-700",
  };
  const tier = event.risk_tier;
  return (
    <li className="text-xs font-mono border-b py-1.5">
      <span className="text-zinc-400">{event.ts}</span>{" "}
      <span className="text-zinc-600">{event.category}</span>{" "}
      {tier ? (
        <span className={tierColour[tier]}>[{tier}]</span>
      ) : null}{" "}
      <span>{event.action_type ?? ""}</span>{" "}
      {event.duration_ms != null ? (
        <span className="text-zinc-500">{event.duration_ms} ms</span>
      ) : null}{" "}
      {event.warden_decision && event.warden_decision !== "allow" ? (
        <span className="text-red-700">[{event.warden_decision}]</span>
      ) : null}
    </li>
  );
}

function PermissionRow({ prompt }: { prompt: ReturnType<typeof readPrompt> }) {
  const resolve = useCockpitStore((s) => s.resolvePermissionPrompt);
  const decide = async (approved: boolean) => {
    // M5 audit-fix wave: always remove the prompt from local state even when
    // the REST call fails — ghost prompts stuck in the UI are worse than the
    // operator's repeat attempt. Errors get surfaced via console.warn.
    try {
      const response = await fetch(`/api/body/permissions/${prompt.request_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved, reason: "ui_decision" }),
      });
      if (!response.ok) {
        console.warn(
          "permission decision failed",
          prompt.request_id,
          response.status,
        );
      }
    } catch (err) {
      console.warn("permission decision threw", prompt.request_id, err);
    } finally {
      resolve(prompt.request_id);
    }
  };
  return (
    <li className="border rounded p-3 space-y-2 text-sm">
      <div className="font-mono">
        {prompt.action_type} <span className="text-zinc-500">[{prompt.risk_tier}]</span>
      </div>
      <div className="text-xs text-zinc-500">{prompt.target_uri ?? ""}</div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => decide(true)}
          className="rounded px-3 py-1 bg-green-600 text-white hover:bg-green-700"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={() => decide(false)}
          className="rounded px-3 py-1 bg-red-600 text-white hover:bg-red-700"
        >
          Deny
        </button>
      </div>
    </li>
  );
}

function readPrompt(p: { request_id: string; action_type: string; risk_tier: string; target_uri: string | null; }) {
  return p;
}

export default function BodyPage() {
  const sessions = useCockpitStore((s) => s.bodySessions);
  const events = useCockpitStore((s) => s.bodyEvents);
  const prompts = useCockpitStore((s) => s.bodyPrompts);
  const p50 = useCockpitStore((s) => s.bodyLatencyP50Ms);
  const p95 = useCockpitStore((s) => s.bodyLatencyP95Ms);

  return (
    <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-6">
      <section className="space-y-3">
        <h2 className="font-semibold">Active Sessions</h2>
        {sessions.length === 0 ? (
          <div className="text-sm text-zinc-500">No active body sessions.</div>
        ) : (
          sessions.map((s) => <SessionCard key={s.session_id} session={s} />)
        )}
      </section>
      <section className="space-y-3">
        <h2 className="font-semibold">Action Stream</h2>
        <div className="text-xs text-zinc-500">
          Vision latency p50 {p50 ?? "—"} ms · p95 {p95 ?? "—"} ms
        </div>
        <ul className="max-h-[60vh] overflow-y-auto pr-2">
          {events.slice().reverse().map((event) => (
            <EventRow key={event.id} event={event} />
          ))}
        </ul>
      </section>
      <section className="space-y-3">
        <h2 className="font-semibold">Pending Approvals</h2>
        {prompts.length === 0 ? (
          <div className="text-sm text-zinc-500">No pending prompts.</div>
        ) : (
          <ul className="space-y-2">
            {prompts.map((prompt) => (
              <PermissionRow key={prompt.request_id} prompt={readPrompt(prompt)} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
