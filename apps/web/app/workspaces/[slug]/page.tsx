/**
 * Workspace dynamic route — server wrapper.
 *
 * Next.js 15 with `output: 'export'` requires `generateStaticParams`
 * on every dynamic route. The actual page is a client component
 * (`WorkspaceClient`) because it owns the WebSocket + poll lifecycles;
 * this thin server wrapper only exists to surface the static-params
 * contract.
 *
 * Build-time: returns the empty list (the export bundle only ships
 * the route shell; actual workspaces resolve at runtime against the
 * orchestrator).
 *
 * Runtime: ``dynamicParams = true`` makes the dev server (and any
 * runtime renderer if we ever switch off pure static export) render
 * unknown slugs on demand.
 */

import { WorkspaceClient } from "./workspace-client";

export function generateStaticParams(): Array<{ slug: string }> {
  return [];
}

// In static export builds, only the slugs returned by generateStaticParams
// are pre-rendered; the rest 404. In dev (next dev), every slug renders on
// demand. We set dynamicParams=false explicitly so Next.js doesn't try to
// reconcile it with output: 'export'.
export const dynamicParams = false;

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <WorkspaceClient slug={slug} />;
}
