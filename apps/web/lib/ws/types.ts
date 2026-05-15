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
  | "provider_auth_status";

export interface WsEnvelope<TPayload = Record<string, unknown>> {
  seq: number;
  event_type: WsEventType;
  session_id?: string | null;
  project_slug?: string | null;
  payload: TPayload;
  ts: string;
}
