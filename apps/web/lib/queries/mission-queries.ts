/**
 * TanStack Query bindings for Mission tab data — Order 6.
 *
 * The kanban query has ``staleTime: Infinity`` (M-2 architectural
 * decision) — the WS subscription is responsible for keeping the
 * cache fresh via ``setQueryData``. The board never silently
 * refetches when the user clicks back into the tab.
 */
import { useQuery } from "@tanstack/react-query";

import {
  getKanban,
  getProject,
  listProjects,
  resumeNow,
  type KanbanResponse,
  type ProjectResponse,
  type RunRequestResponse,
} from "@/lib/api";
import { cockpitKeys } from "@/lib/query";

export function useProjectsQuery() {
  return useQuery<ProjectResponse[]>({
    queryKey: cockpitKeys.projects(),
    queryFn: () => listProjects(),
  });
}

export function useProjectQuery(slug: string | null) {
  return useQuery<ProjectResponse>({
    queryKey: slug ? cockpitKeys.project(slug) : ["__noop_project__"],
    queryFn: () => {
      if (!slug) {
        throw new Error("project slug is required");
      }
      return getProject(slug);
    },
    enabled: slug !== null,
  });
}

export function useKanbanQuery(slug: string | null) {
  return useQuery<KanbanResponse>({
    queryKey: slug ? cockpitKeys.kanban(slug) : ["__noop_kanban__"],
    queryFn: () => {
      if (!slug) {
        throw new Error("project slug is required");
      }
      return getKanban(slug);
    },
    enabled: slug !== null,
  });
}

export async function resumePausedSession(
  sessionId: string,
): Promise<RunRequestResponse> {
  return resumeNow(sessionId);
}
