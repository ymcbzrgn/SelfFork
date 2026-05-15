/**
 * Settings — Stitch-verbatim port. Two sections (Notifications +
 * Privacy) with toggle rows + Advanced link. Stitch's bonus bento
 * row at the bottom (Security Health + Data Usage) is kept.
 *
 * Backend: future /api/settings/general. Toggles are local-only
 * (localStorage) for now — when the orchestrator exposes them we'll
 * swap to a real fetch. The Advanced link routes to the engineering
 * vision-adapter surface that still lives under /cockpit/.
 */
"use client";

import Link from "next/link";
import { ArrowRight, BarChart3, Shield } from "lucide-react";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Switch } from "@/components/ui/switch";

interface UserPrefs {
  notify_on_finish: boolean;
  email_weekly_summary: boolean;
  desktop_alerts: boolean;
  ai_learns_from_data: boolean;
  share_anonymous_stats: boolean;
  profile_visible: boolean;
}

const STORAGE_KEY = "selffork.user_prefs.v1";

const DEFAULT_PREFS: UserPrefs = {
  notify_on_finish: false,
  email_weekly_summary: false,
  desktop_alerts: false,
  ai_learns_from_data: false,
  share_anonymous_stats: false,
  profile_visible: false,
};

function loadPrefs(): UserPrefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    return { ...DEFAULT_PREFS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_PREFS;
  }
}

function persist(prefs: UserPrefs): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // localStorage may be disabled; silently no-op.
  }
}

interface RowProps {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}

function Row({ label, value, onChange }: RowProps) {
  return (
    <div className="flex items-center justify-between p-card-padding hover:bg-surface-muted/50 transition-colors">
      <span className="font-body text-body text-on-surface-variant pr-6">
        {label}
      </span>
      <Switch
        checked={value}
        onCheckedChange={onChange}
        className="data-[state=checked]:bg-primary"
      />
    </div>
  );
}

export default function SettingsPage() {
  const [prefs, setPrefs] = useState<UserPrefs>(DEFAULT_PREFS);

  useEffect(() => {
    setPrefs(loadPrefs());
  }, []);

  const update = <K extends keyof UserPrefs>(key: K, value: UserPrefs[K]) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value };
      persist(next);
      return next;
    });
  };

  return (
    <AppShell title="Personal Space">
      <main className="flex-1">
        <div className="px-gutter-desktop py-8 max-w-[960px] mx-auto w-full">
          <h1 className="font-display text-display text-on-surface mb-12">
            Settings
          </h1>

          <div className="flex flex-col gap-vertical-gap">
            <section>
              <h2 className="font-heading text-heading mb-4 text-on-surface">
                Notifications
              </h2>
              <div className="bg-surface rounded-xl shadow-[0_2px_8px_rgba(15,23,42,0.04)] overflow-hidden divide-y divide-border/40">
                <Row
                  label="Notify me when a project finishes"
                  value={prefs.notify_on_finish}
                  onChange={(v) => update("notify_on_finish", v)}
                />
                <Row
                  label="Email me weekly summaries of my workspace activity"
                  value={prefs.email_weekly_summary}
                  onChange={(v) => update("email_weekly_summary", v)}
                />
                <Row
                  label="Show desktop alerts for agent messages"
                  value={prefs.desktop_alerts}
                  onChange={(v) => update("desktop_alerts", v)}
                />
              </div>
            </section>

            <section>
              <h2 className="font-heading text-heading mb-4 text-on-surface">
                Privacy
              </h2>
              <div className="bg-surface rounded-xl shadow-[0_2px_8px_rgba(15,23,42,0.04)] overflow-hidden divide-y divide-border/40">
                <Row
                  label="Allow AI assistants to learn from my project data"
                  value={prefs.ai_learns_from_data}
                  onChange={(v) => update("ai_learns_from_data", v)}
                />
                <Row
                  label="Share anonymous usage statistics to help improve SelfFork"
                  value={prefs.share_anonymous_stats}
                  onChange={(v) => update("share_anonymous_stats", v)}
                />
                <Row
                  label="Make my profile visible to other creators in the community"
                  value={prefs.profile_visible}
                  onChange={(v) => update("profile_visible", v)}
                />
              </div>
            </section>

            <div className="mt-4">
              <Link
                href="/cockpit/settings/vision"
                className="font-body text-body text-foreground-muted hover:text-primary transition-colors flex items-center gap-1 group w-fit"
              >
                Advanced settings
                <ArrowRight
                  className="h-[18px] w-[18px] group-hover:translate-x-1 transition-transform"
                  strokeWidth={1.75}
                />
              </Link>
            </div>
          </div>

          <div className="mt-16 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-surface-container-low p-6 rounded-xl border border-border/40 flex flex-col gap-2">
              <Shield className="h-5 w-5 text-primary" strokeWidth={1.75} />
              <h3 className="font-heading text-body font-semibold text-on-surface">
                Security Health
              </h3>
              <p className="font-body text-caption text-foreground-muted">
                Single-operator local instance. Sign-in flows persist as
                Playwright storage_state per project.
              </p>
            </div>
            <div className="bg-surface-container-low p-6 rounded-xl border border-border/40 flex flex-col gap-2">
              <BarChart3 className="h-5 w-5 text-tertiary" strokeWidth={1.75} />
              <h3 className="font-heading text-body font-semibold text-on-surface">
                Data Usage
              </h3>
              <p className="font-body text-caption text-foreground-muted">
                Workspace artifacts live under <code className="font-mono text-[12px]">~/.selffork/projects/</code>.
              </p>
            </div>
          </div>
        </div>
      </main>
    </AppShell>
  );
}
