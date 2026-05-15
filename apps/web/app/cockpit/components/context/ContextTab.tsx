/**
 * Context tab root — Order 9.
 *
 * Surfaces the project's Mind state as six native-tier collapsible
 * sections (T1 Working through T6 Recall) plus an interactive recall
 * query bar. Tier counts come from ``GET /api/projects/<slug>/mind/stats``;
 * note lists come from ``GET .../mind/notes?tier=...``. T3 Semantic
 * Graph renders a placeholder — the D3 force-graph view is M5+.
 */
"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  getMindStats,
  listMindNotes,
  type MindStatsResponse,
  type NoteResponse,
  type ProjectResponse,
  listProjects,
} from "@/lib/api";
import { cockpitKeys } from "@/lib/query";
import { useCockpitStore, type MindTier } from "@/lib/store";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";

import { NoteList } from "./NoteList";
import { RecallQueryBar } from "./RecallQueryBar";
import { TierSection } from "./TierSection";

const TIER_TITLE: Record<MindTier, string> = {
  working: "Working",
  episodic: "Episodic",
  semantic_graph: "Semantic graph",
  procedural: "Procedural",
  reflection: "Reflection",
  recall: "Recall",
};

const TIER_ORDER: MindTier[] = [
  "working",
  "episodic",
  "semantic_graph",
  "procedural",
  "reflection",
  "recall",
];

export function ContextTab() {
  const projectsQuery = useQuery<ProjectResponse[]>({
    queryKey: cockpitKeys.projects(),
    queryFn: listProjects,
  });
  const activeProjectSlug = useCockpitStore(
    (s) => s.contextActiveProjectSlug,
  );
  const setActiveProject = useCockpitStore(
    (s) => s.setContextActiveProject,
  );

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
      <ProjectPicker
        projects={projectsQuery.data ?? []}
        activeSlug={activeProjectSlug}
        loading={projectsQuery.isPending}
        onChange={setActiveProject}
      />
      {activeProjectSlug !== null ? (
        <RecallQueryBar slug={activeProjectSlug} />
      ) : null}
      <ContextBody activeProjectSlug={activeProjectSlug} />
    </div>
  );
}

function ProjectPicker({
  projects,
  activeSlug,
  loading,
  onChange,
}: {
  projects: ProjectResponse[];
  activeSlug: string | null;
  loading: boolean;
  onChange: (slug: string | null) => void;
}) {
  if (loading) return <Skeleton className="h-9 w-72" />;
  if (projects.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No projects yet — create one from the Mission tab.
      </p>
    );
  }
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Project</span>
      <select
        aria-label="Active context project"
        value={activeSlug ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="rounded-md border border-border bg-card px-2 py-1 text-sm"
      >
        {projects.map((p) => (
          <option key={p.slug} value={p.slug}>
            {p.name} ({p.slug})
          </option>
        ))}
      </select>
    </label>
  );
}

function ContextBody({
  activeProjectSlug,
}: {
  activeProjectSlug: string | null;
}) {
  if (activeProjectSlug === null) {
    return (
      <EmptyState
        title="No project selected"
        hint="Pick a project above to load its Mind state."
      />
    );
  }
  return <ProjectContext slug={activeProjectSlug} />;
}

function ProjectContext({ slug }: { slug: string }) {
  const statsQuery = useQuery<MindStatsResponse>({
    queryKey: cockpitKeys.mindStats(slug),
    queryFn: () => getMindStats(slug),
  });
  if (statsQuery.isPending) {
    return <Skeleton className="h-96 w-full" data-testid="context-loading" />;
  }
  const tiers = statsQuery.data?.tiers ?? {};
  return (
    <div className="space-y-3" data-testid="context-tier-list">
      {TIER_ORDER.map((tier) => {
        const stat = tiers[tier];
        return (
          <TierSection
            key={tier}
            tier={tier}
            title={TIER_TITLE[tier]}
            count={stat?.count ?? 0}
            lastUpdated={stat?.last_updated ?? null}
          >
            {tier === "semantic_graph" ? (
              <p className="text-xs text-muted-foreground">
                Force-graph view ships in M5+. For now the tier count
                + recall search are the operator surface.
              </p>
            ) : (
              <TierNotes slug={slug} tier={tier} count={stat?.count ?? 0} />
            )}
          </TierSection>
        );
      })}
    </div>
  );
}

function TierNotes({
  slug,
  tier,
  count,
}: {
  slug: string;
  tier: MindTier;
  count: number;
}) {
  const notesQuery = useQuery<NoteResponse[]>({
    queryKey: cockpitKeys.mindNotes(slug, tier),
    queryFn: () => listMindNotes(slug, tier),
    enabled: count > 0,
  });
  if (count === 0) {
    return (
      <p className="text-xs text-muted-foreground">No notes yet.</p>
    );
  }
  if (notesQuery.isPending) {
    return <Skeleton className="h-24 w-full" />;
  }
  return <NoteList notes={notesQuery.data ?? []} />;
}
