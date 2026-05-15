/**
 * AppShell v2 — fixed sidebar + main column that respects sidebar width.
 *
 * Matches the Stitch reference layout: sidebar is `position: fixed` so
 * pages can scroll their own content without affecting nav, and the
 * main column carries `md:ml-sidebar-width` so the content never slides
 * under the rail. No outer page padding or max-width — each route owns
 * its own gutter via `px-gutter-desktop` so Stitch-faithful spacing
 * stays consistent.
 */
import { Sidebar } from "./sidebar";
import { TopBar } from "./topbar";

export function AppShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main className="md:ml-sidebar-width min-h-screen flex flex-col">
        <TopBar title={title} />
        <div className="flex-1">{children}</div>
      </main>
    </div>
  );
}
