/**
 * Mission tab root — Order 6.
 *
 * Lays out: project selector + KanbanBoard + SessionDrawer. WS-driven
 * cache updates push fresh kanban snapshots into the TanStack Query
 * cache without polling. Card click opens a side-drawer with session
 * detail; orchestrator owns status transitions, the cockpit is
 * read-mostly (only ``blocked → pending`` is operator-driven).
 */
"use client";

import { useEffect } from "react";

import { kanbanStreamUrl } from "@/lib/api";
import { cockpitKeys, queryClient } from "@/lib/query";
import {
  useKanbanQuery,
  useProjectsQuery,
} from "@/lib/queries/mission-queries";
import { useCockpitStore } from "@/lib/store";
import { useWebsocketSubscription } from "@/lib/ws/multiplex";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";

import { KanbanBoard } from "./KanbanBoard";
import { ProjectSelector } from "./ProjectSelector";
import { SessionDrawer } from "./SessionDrawer";

export function MissionTab() {
  const projectsQuery = useProjectsQuery();
  const activeProjectSlug = useCockpitStore(
    (s) => s.missionActiveProjectSlug,
  );
  const setActiveProject = useCockpitStore(
    (s) => s.setMissionActiveProject,
  );

  // Default to the first project on first render so the cockpit
  // doesn't render an empty state until the operator clicks.
  useEffect(() => {
    if (
      activeProjectSlug === null &&
      projectsQuery.data &&
      projectsQuery.data.length > 0
    ) {
      setActiveProject(projectsQuery.data[0].slug);
    }
  }, [activeProjectSlug, projectsQuery.data, setActiveProject]);

  return (
    <div className="space-y-4">
      <ProjectSelector
        projects={projectsQuery.data ?? []}
        activeSlug={activeProjectSlug}
        onChange={setActiveProject}
        loading={projectsQuery.isPending}
      />
      <MissionBody activeProjectSlug={activeProjectSlug} />
      <SessionDrawer />
    </div>
  );
}

function MissionBody({
  activeProjectSlug,
}: {
  activeProjectSlug: string | null;
}) {
  if (activeProjectSlug === null) {
    return (
      <EmptyState
        title="No project selected"
        hint="Pick a project above to load its kanban."
      />
    );
  }
  return <ProjectKanban slug={activeProjectSlug} />;
}

function ProjectKanban({ slug }: { slug: string }) {
  const kanbanQuery = useKanbanQuery(slug);

  // WS subscription — every server-side mutation pushes a new board
  // snapshot which we splice straight into the TanStack Query cache.
  useWebsocketSubscription({
    url: kanbanStreamUrl(slug),
    onEnvelope: (env) => {
      // Kanban WS still emits raw KanbanResponse JSON (M-1 envelope
      // wrapping is a future Order 7 task for consistency); when
      // ``event_type`` is missing we treat the whole payload as the
      // KanbanResponse, otherwise we read ``payload``.
      const next = env.event_type === "kanban" ? env.payload : env;
      queryClient.setQueryData(cockpitKeys.kanban(slug), next);
    },
  });

  if (kanbanQuery.isPending) {
    return <Skeleton className="h-96 w-full" data-testid="mission-loading" />;
  }
  if (kanbanQuery.isError) {
    return (
      <ErrorState
        title="Could not load kanban"
        detail={String(kanbanQuery.error)}
      />
    );
  }
  if (!kanbanQuery.data) return null;
  return <KanbanBoard slug={slug} board={kanbanQuery.data} />;
}
