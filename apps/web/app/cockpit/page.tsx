/**
 * Cockpit ``/cockpit`` page — 4-tab shell wired to URL state.
 *
 * All four tabs (Mission/Run/Chat/Context) render their real content;
 * the shell owns URL ↔ store tab sync so deep links and non-Tabs
 * surfaces (e.g. the command palette) stay in lockstep.
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
  providers: "Providers",
  fleet: "Fleet",
  body: "Body",
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
