/**
 * Typed wrappers around the SelfFork dashboard backend.
 *
 * Per ``project_ui_stack.md`` the backend is the single source of truth
 * for everything on screen. We never hardcode mock data here.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export interface DashboardHealth {
  status: string;
  audit_dir: string;
  resume_dir: string;
}

export interface PausedSession {
  session_id: string;
  scheduled_at: string;
  resume_at: string;
  cli_agent: string;
  config_path: string | null;
  prd_path: string;
  workspace_path: string;
  reason: string;
  kind: string;
  is_due: boolean;
}

export interface RecentSession {
  session_id: string;
  started_at: string;
  last_event_at: string;
  final_state: string | null;
  rounds_observed: number;
  cli_agent: string | null;
}

export interface AuditEvent {
  ts: string;
  category: string;
  level: string;
  event: string;
  payload: Record<string, unknown>;
}

export interface PlanSnapshot {
  schema_version: number;
  summary: string;
  sub_tasks: Array<Record<string, unknown>>;
}

export interface WorkspaceEntry {
  path: string;
  kind: "file" | "dir";
  size_bytes: number | null;
  modified_at: string | null;
}

export interface RunRequestResponse {
  status: string;
  pid: number | null;
  detail: string | null;
}

export interface ProjectResponse {
  slug: string;
  name: string;
  description: string;
  root_path: string | null;
  created_at: string;
  updated_at: string;
  card_counts: Record<string, number>;
}

export interface KanbanCardResponse {
  id: string;
  title: string;
  body: string;
  column: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  last_touched_by_session_id: string | null;
  order: number | null;
}

export interface KanbanResponse {
  schema_version: number;
  columns: string[];
  cards_by_column: Record<string, KanbanCardResponse[]>;
}

export interface ProviderUsage {
  cli_agent: "claude-code" | "gemini-cli" | "opencode" | "codex";
  window_label: string;
  window_seconds: number;
  calls_in_window: number;
  next_reset_at: string | null;
  last_rate_limited_at: string | null;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // ignore body parse errors
    }
    throw new ApiError(res.status, detail);
  }
  // 204 (No Content) responses can't be JSON-parsed.
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export function getHealth(): Promise<DashboardHealth> {
  return request<DashboardHealth>("/api/health");
}

export function listPausedSessions(): Promise<PausedSession[]> {
  return request<PausedSession[]>("/api/sessions/paused");
}

export function listRecentSessions(): Promise<RecentSession[]> {
  return request<RecentSession[]>("/api/sessions/recent");
}

export function getSessionEvents(sessionId: string): Promise<AuditEvent[]> {
  return request<AuditEvent[]>(`/api/sessions/${sessionId}/events`);
}

export function getSessionPlan(sessionId: string): Promise<PlanSnapshot> {
  return request<PlanSnapshot>(`/api/sessions/${sessionId}/plan`);
}

export function getSessionWorkspace(
  sessionId: string,
): Promise<WorkspaceEntry[]> {
  return request<WorkspaceEntry[]>(`/api/sessions/${sessionId}/workspace`);
}

export function startRun(
  prdPath: string,
  configPath?: string,
  projectSlug?: string,
): Promise<RunRequestResponse> {
  return request<RunRequestResponse>("/api/sessions/run", {
    method: "POST",
    body: JSON.stringify({
      prd_path: prdPath,
      config_path: configPath ?? null,
      project_slug: projectSlug ?? null,
    }),
  });
}

export function resumeNow(sessionId: string): Promise<RunRequestResponse> {
  return request<RunRequestResponse>(
    `/api/sessions/paused/${sessionId}/resume`,
    { method: "POST" },
  );
}

// ── Projects ─────────────────────────────────────────────────────────────────

export function listProjects(): Promise<ProjectResponse[]> {
  return request<ProjectResponse[]>("/api/projects");
}

export function createProject(payload: {
  name: string;
  description?: string;
  root_path?: string | null;
}): Promise<ProjectResponse> {
  return request<ProjectResponse>("/api/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProject(slug: string): Promise<ProjectResponse> {
  return request<ProjectResponse>(`/api/projects/${slug}`);
}

export function getKanban(slug: string): Promise<KanbanResponse> {
  return request<KanbanResponse>(`/api/projects/${slug}/kanban`);
}

export function addKanbanCard(
  slug: string,
  payload: { title: string; body?: string; column?: string },
): Promise<KanbanCardResponse> {
  return request<KanbanCardResponse>(`/api/projects/${slug}/kanban/cards`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function moveKanbanCard(
  slug: string,
  cardId: string,
  toColumn: string,
): Promise<KanbanCardResponse> {
  return request<KanbanCardResponse>(
    `/api/projects/${slug}/kanban/cards/${cardId}/move`,
    {
      method: "PATCH",
      body: JSON.stringify({ to_column: toColumn }),
    },
  );
}

export function updateKanbanCard(
  slug: string,
  cardId: string,
  patch: { title?: string; body?: string },
): Promise<KanbanCardResponse> {
  return request<KanbanCardResponse>(
    `/api/projects/${slug}/kanban/cards/${cardId}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export function deleteKanbanCard(slug: string, cardId: string): Promise<void> {
  return request<void>(`/api/projects/${slug}/kanban/cards/${cardId}`, {
    method: "DELETE",
  });
}

// ── Provider usage ───────────────────────────────────────────────────────────

export function listProviderUsage(): Promise<ProviderUsage[]> {
  return request<ProviderUsage[]>("/api/usage/providers");
}

// ── Live audit ───────────────────────────────────────────────────────────────

export function openSessionStream(sessionId: string): WebSocket {
  const httpBase =
    API_BASE !== ""
      ? API_BASE
      : typeof window !== "undefined"
        ? window.location.origin
        : "";
  const wsBase = httpBase.replace(/^http/, "ws");
  return new WebSocket(`${wsBase}/api/sessions/${sessionId}/stream`);
}

export { ApiError };
