/**
 * Typed wrappers around the SelfFork dashboard backend.
 *
 * Per ``project_ui_stack.md`` the backend is the single source of truth
 * for everything on screen. We never hardcode mock data here.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

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

// String-only URL builder — never opens a socket. Used by
// ``useWebsocketSubscription`` (which is the sole owner of the
// connection). Order 6/8 audit caught a leak where ``open*Stream``
// factories were called for their ``.url`` and the spawned socket
// was orphaned.
function _wsBase(): string {
  const httpBase =
    API_BASE !== ""
      ? API_BASE
      : typeof window !== "undefined"
        ? window.location.origin
        : "";
  return httpBase.replace(/^http/, "ws");
}

export function sessionStreamUrl(sessionId: string): string {
  return `${_wsBase()}/api/sessions/${sessionId}/stream`;
}

export function kanbanStreamUrl(slug: string): string {
  return `${_wsBase()}/api/projects/${slug}/kanban/stream`;
}

// Legacy factories — they DO open a real socket and the caller is
// responsible for ``close()``. Used by the pre-cockpit
// ``apps/web/app/session/page.tsx`` and ``app/project/page.tsx`` which
// own their own lifecycle. New cockpit surfaces (Order 6+) must use
// the URL builders + ``useWebsocketSubscription``, never these.
export function openSessionStream(sessionId: string): WebSocket {
  return new WebSocket(sessionStreamUrl(sessionId));
}

export function openKanbanStream(slug: string): WebSocket {
  return new WebSocket(kanbanStreamUrl(slug));
}

// ── Chat surface — Order 4 / Order 8 ─────────────────────────────────────────

export interface BranchResponse {
  id: string;
  session_id: string;
  parent_branch_id: string | null;
  fork_message_id: string | null;
  label: string;
  is_active: boolean;
  created_at: string;
}

export interface ChatMessageResponse {
  id: string;
  branch_id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  parent_message_id: string | null;
  created_at: string;
}

export function listBranches(sessionId: string): Promise<BranchResponse[]> {
  return request<BranchResponse[]>(`/api/sessions/${sessionId}/branches`);
}

export function listMessages(
  sessionId: string,
  branchId?: string,
): Promise<ChatMessageResponse[]> {
  const qs = branchId ? `?branch_id=${encodeURIComponent(branchId)}` : "";
  return request<ChatMessageResponse[]>(
    `/api/sessions/${sessionId}/messages${qs}`,
  );
}

export function postChatMessage(
  sessionId: string,
  payload: { content: string; role?: "user" | "assistant" | "tool"; branch_id?: string },
): Promise<ChatMessageResponse> {
  return request<ChatMessageResponse>(`/api/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function editChatMessage(
  sessionId: string,
  messageId: string,
  payload: { content: string; branch_label?: string },
): Promise<BranchResponse> {
  return request<BranchResponse>(
    `/api/sessions/${sessionId}/messages/${messageId}/edit`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function setActiveBranch(
  sessionId: string,
  branchId: string,
): Promise<BranchResponse> {
  return request<BranchResponse>(
    `/api/sessions/${sessionId}/active-branch`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ branch_id: branchId }),
    },
  );
}

export function chatStreamUrl(sessionId: string): string {
  return `${_wsBase()}/api/sessions/${sessionId}/chat/stream`;
}

export function openChatStream(sessionId: string): WebSocket {
  return new WebSocket(chatStreamUrl(sessionId));
}

// ── Mind HTTP surface — Order 3 / Order 9 ───────────────────────────────────

export interface MindTierStatsRow {
  count: number;
  last_updated: string | null;
}

export interface MindStatsResponse {
  tiers: Record<string, MindTierStatsRow>;
}

export interface NoteResponse {
  id: string;
  tier: string;
  kind: string;
  content: string;
  intent: string;
  importance: number;
  pinned: boolean;
  project_slug: string | null;
  session_id: string | null;
  valid_from: string;
  valid_until: string | null;
  tag_keys: string[];
  path_scope: string[];
  always_apply: boolean;
}

export interface MindRecallResponse {
  hits: NoteResponse[];
  scores: number[];
}

export function getMindStats(slug: string): Promise<MindStatsResponse> {
  return request<MindStatsResponse>(
    `/api/projects/${slug}/mind/stats`,
  );
}

export function listMindNotes(
  slug: string,
  tier?: string,
  limit = 50,
): Promise<NoteResponse[]> {
  const params = new URLSearchParams();
  if (tier) params.set("tier", tier);
  params.set("limit", String(limit));
  return request<NoteResponse[]>(
    `/api/projects/${slug}/mind/notes?${params.toString()}`,
  );
}

export function recallMind(
  slug: string,
  payload: {
    query: string;
    tier?: string;
    top_k?: number;
    threshold?: number;
    session_id?: string;
  },
): Promise<MindRecallResponse> {
  return request<MindRecallResponse>(
    `/api/projects/${slug}/mind/recall`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function mindProvenanceStreamUrl(slug: string): string {
  return `${_wsBase()}/api/projects/${slug}/mind/provenance/stream`;
}

export function openMindProvenanceStream(slug: string): WebSocket {
  return new WebSocket(mindProvenanceStreamUrl(slug));
}

export interface ProvenanceEntry {
  ts: string;
  correlation_id: string;
  session_id: string;
  project_slug: string | null;
  query: string;
  note_ids: string[];
  scores: number[];
  retriever: string;
  reranker: string | null;
}

export function listProjectProvenance(
  slug: string,
  limit = 100,
): Promise<ProvenanceEntry[]> {
  return request<ProvenanceEntry[]>(
    `/api/projects/${slug}/mind/provenance?limit=${limit}`,
  );
}

export function listOrphanProvenance(limit = 100): Promise<ProvenanceEntry[]> {
  return request<ProvenanceEntry[]>(`/api/mind/provenance?limit=${limit}`);
}

export { ApiError };
