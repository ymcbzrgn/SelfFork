/**
 * TypeScript mirror of the M-1 ``WsEnvelope`` Pydantic model — Order 5.
 *
 * Kept in sync by hand (the OpenAPI generator covers REST schemas but
 * Starlette doesn't surface WS schemas there). Source of truth:
 * ``packages/orchestrator/src/selffork_orchestrator/dashboard/ws_protocol.py``.
 */

export type WsEventType =
  | "audit"
  | "kanban"
  | "quota"
  | "mind"
  | "chat.token"
  | "heartbeat"
  | "gap"
  | "fleet_status"
  | "body_action"
  | "body_observation"
  | "provider_auth_status"
  // M6 Talk surface (ADR-007 §4 S1) + S-Stream token streaming (ADR-011).
  | "talk.message"
  | "talk.token"
  | "talk.error"
  | "talk.cancelled"
  // M6 Live Run Theater (ADR-007 §4 S2).
  | "snapshot"
  | "cli.output.append"
  | "thought.new";

export interface WsEnvelope<TPayload = Record<string, unknown>> {
  seq: number;
  event_type: WsEventType;
  session_id?: string | null;
  project_slug?: string | null;
  payload: TPayload;
  ts: string;
}
