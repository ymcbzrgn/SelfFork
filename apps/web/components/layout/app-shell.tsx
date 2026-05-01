/**
 * Three-column-ish app shell: sidebar (fixed) + main column (topbar + page).
 *
 * The page passes a ``title`` rendered into the topbar so the user
 * always sees where they are without us hardcoding it inside each
 * page module.
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
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar title={title} />
        <main className="flex-1 overflow-y-auto px-6 py-6 lg:px-8 lg:py-8 scrollbar-thin">
          <div className="mx-auto max-w-7xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
