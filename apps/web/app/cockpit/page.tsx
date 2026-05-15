/**
 * Cockpit ``/cockpit`` page — 4-tab shell wired to URL state.
 *
 * Order 5 lays the tab structure with placeholder bodies so subsequent
 * orders can paint the real Mission/Run/Chat/Context content without
 * touching shell wiring. Each tab placeholder renders a banner so the
 * operator always knows which surface they're looking at, even before
 * later orders ship.
 */
"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { ChatTab } from "@/app/cockpit/components/chat/ChatTab";
import { ContextTab } from "@/app/cockpit/components/context/ContextTab";
import { MissionTab } from "@/app/cockpit/components/mission/MissionTab";
import { RunTab } from "@/app/cockpit/components/run/RunTab";
import {
  type CockpitTab,
  useCockpitStore,
} from "@/lib/store";

const TAB_ORDER: CockpitTab[] = ["mission", "run", "chat", "context"];
const TAB_LABEL: Record<CockpitTab, string> = {
  mission: "Mission",
  run: "Run",
  chat: "Chat",
  context: "Context",
};

function isCockpitTab(value: string | null): value is CockpitTab {
  return value !== null && (TAB_ORDER as string[]).includes(value);
}

export default function CockpitPage() {
  const search = useSearchParams();
  const router = useRouter();
  const setActiveTab = useCockpitStore((s) => s.setActiveTab);
  const activeTab = useCockpitStore((s) => s.activeTab);

  // URL ↔ store sync. URL is the source of truth on first load (deep
  // link); the store stays in lockstep so non-Tabs surfaces (e.g. the
  // command palette) can read activeTab without re-parsing the URL.
  const urlTab = search.get("tab");
  const resolvedTab: CockpitTab = isCockpitTab(urlTab) ? urlTab : "mission";

  useEffect(() => {
    if (activeTab !== resolvedTab) {
      setActiveTab(resolvedTab);
    }
  }, [resolvedTab, activeTab, setActiveTab]);

  const onTabChange = (next: string) => {
    if (!isCockpitTab(next)) return;
    setActiveTab(next);
    const sp = new URLSearchParams(search.toString());
    sp.set("tab", next);
    router.replace(`/cockpit/?${sp.toString()}`);
  };

  return (
    <Tabs
      value={resolvedTab}
      onValueChange={onTabChange}
      className="space-y-4"
    >
      <TabsList aria-label="Cockpit tabs">
        {TAB_ORDER.map((tab) => (
          <TabsTrigger key={tab} value={tab}>
            {TAB_LABEL[tab]}
          </TabsTrigger>
        ))}
      </TabsList>

      <TabsContent value="mission">
        <MissionTab />
      </TabsContent>
      <TabsContent value="run">
        <RunTab />
      </TabsContent>
      <TabsContent value="chat">
        <ChatTab />
      </TabsContent>
      <TabsContent value="context">
        <ContextTab />
      </TabsContent>
    </Tabs>
  );
}

function CockpitTabPlaceholder({
  tab,
  summary,
}: {
  tab: CockpitTab;
  summary: string;
}) {
  return (
    <div
      className="rounded-md border border-dashed border-border/60 bg-card/40 p-6 text-sm text-muted-foreground"
      data-testid={`cockpit-tab-${tab}-placeholder`}
    >
      <h2 className="text-base font-semibold text-foreground">
        {TAB_LABEL[tab]}
      </h2>
      <p className="mt-2">{summary}</p>
    </div>
  );
}
