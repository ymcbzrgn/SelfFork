/**
 * Home — SelfFork v2, Stitch-verbatim port (Lovable-style entry).
 *
 * Big intent input, recent project chips strip, three exploratory
 * action cards. Mock data is forbidden — recent chips are sourced
 * from real /api/projects; if empty, the strip is hidden (not
 * faked). Submitting the input creates a workspace and routes to
 * Talk with that workspace selected.
 */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Network, Plus, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import {
  createProject,
  listProjects,
  type ProjectResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function StatusDot({ inProgress }: { inProgress: number }) {
  return (
    <span
      className={cn(
        "inline-block w-1.5 h-1.5 rounded-full",
        inProgress > 0 ? "bg-primary-container animate-pulse" : "bg-success",
      )}
    />
  );
}

export default function HomePage() {
  const router = useRouter();
  const [intent, setIntent] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectResponse[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    let cancelled = false;
    listProjects()
      .then((data) => {
        if (!cancelled) setProjects(data);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(`Could not reach SelfFork: ${e.message}`);
          setProjects([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const nameFromIntent = (raw: string): string => {
    const trimmed = raw.trim().replace(/\s+/g, " ");
    const words = trimmed.split(" ").slice(0, 6).join(" ");
    return words.length > 56 ? `${words.slice(0, 53)}…` : words;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const raw = intent.trim();
    if (!raw || creating) return;
    setCreating(true);
    setError(null);
    try {
      const project = await createProject({
        name: nameFromIntent(raw),
        description: raw,
      });
      router.push(`/talk?workspace=${project.slug}`);
    } catch (e) {
      setError(`Could not start: ${(e as Error).message}`);
      setCreating(false);
    }
  };

  const recent = projects?.slice(0, 4) ?? [];

  return (
    <AppShell title="Personal Space">
      <section className="min-h-[calc(100vh-64px)] flex flex-col">
        <div className="flex-1 flex flex-col items-center justify-center px-gutter-desktop -mt-12">
          <form
            onSubmit={submit}
            className="w-full max-w-2xl flex flex-col gap-8"
          >
            <div
              className={cn(
                "relative group flex items-center p-4 bg-surface rounded-xl",
                "shadow-[0_2px_8px_rgba(15,23,42,0.04)]",
                "transition-shadow focus-within:shadow-[0_0_0_1px_theme(colors.primary)]",
              )}
            >
              <input
                ref={inputRef}
                type="text"
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
                disabled={creating}
                className={cn(
                  "w-full bg-transparent border-none focus:ring-0 outline-none",
                  "font-display text-display text-on-surface",
                  "placeholder:text-foreground-muted/40 p-0 disabled:opacity-60",
                )}
                placeholder="What are you building?"
                aria-label="Describe what you want to build"
              />
              <button
                type="submit"
                disabled={!intent.trim() || creating}
                className={cn(
                  "flex items-center justify-center w-12 h-12 rounded-lg",
                  "text-foreground-muted hover:text-primary hover:bg-primary/5",
                  "transition-all opacity-0 group-focus-within:opacity-100",
                  "disabled:opacity-30 disabled:cursor-not-allowed",
                )}
                aria-label="Send"
              >
                <ArrowRight className="h-7 w-7" strokeWidth={1.75} />
              </button>
            </div>
            {error ? (
              <p
                role="alert"
                className="font-caption text-caption text-error -mt-4 text-center"
              >
                {error}
              </p>
            ) : null}

            {recent.length > 0 ? (
              <div className="flex items-center justify-center gap-3 flex-wrap">
                <span className="font-caption text-caption text-foreground-muted mr-1">
                  Recent:
                </span>
                {recent.map((p) => {
                  const inProgress =
                    (p.card_counts?.in_progress ?? 0) +
                    (p.card_counts?.review ?? 0);
                  return (
                    <Link
                      key={p.slug}
                      href={`/talk?workspace=${p.slug}`}
                      className={cn(
                        "px-4 py-1.5 bg-surface-muted hover:bg-surface-container-high",
                        "font-caption text-caption text-on-surface-variant rounded-full",
                        "transition-colors flex items-center gap-2 border border-transparent",
                        "hover:border-outline-variant/30",
                      )}
                    >
                      <StatusDot inProgress={inProgress} />
                      {p.name}
                    </Link>
                  );
                })}
              </div>
            ) : null}
          </form>
        </div>

        <div className="px-gutter-desktop pb-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-6xl mx-auto">
            <Link
              href="/workspaces"
              className="group bg-surface p-card-padding rounded-xl shadow-[0_2px_8px_rgba(15,23,42,0.04)] hover:-translate-y-[2px] hover:shadow-[0_4px_12px_rgba(15,23,42,0.08)] transition-all duration-200"
            >
              <div className="w-10 h-10 rounded-lg bg-surface-muted flex items-center justify-center text-foreground-muted mb-4 group-hover:text-primary transition-colors">
                <Plus className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <h3 className="font-heading text-[16px] text-on-surface mb-1">
                New Workspace
              </h3>
              <p className="font-body text-caption text-foreground-muted">
                Start a fresh canvas for your next big idea.
              </p>
            </Link>

            <Link
              href="/talk"
              className="group bg-surface p-card-padding rounded-xl shadow-[0_2px_8px_rgba(15,23,42,0.04)] hover:-translate-y-[2px] hover:shadow-[0_4px_12px_rgba(15,23,42,0.08)] transition-all duration-200"
            >
              <div className="w-10 h-10 rounded-lg bg-surface-muted flex items-center justify-center text-foreground-muted mb-4 group-hover:text-primary transition-colors">
                <Sparkles className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <h3 className="font-heading text-[16px] text-on-surface mb-1">
                Talk to Architect
              </h3>
              <p className="font-body text-caption text-foreground-muted">
                Map out system requirements with AI assistance.
              </p>
            </Link>

            <Link
              href="/connections"
              className="group bg-surface p-card-padding rounded-xl shadow-[0_2px_8px_rgba(15,23,42,0.04)] hover:-translate-y-[2px] hover:shadow-[0_4px_12px_rgba(15,23,42,0.08)] transition-all duration-200"
            >
              <div className="w-10 h-10 rounded-lg bg-surface-muted flex items-center justify-center text-foreground-muted mb-4 group-hover:text-primary transition-colors">
                <Network className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <h3 className="font-heading text-[16px] text-on-surface mb-1">
                Review Connections
              </h3>
              <p className="font-body text-caption text-foreground-muted">
                See who else is building in your ecosystem.
              </p>
            </Link>
          </div>
        </div>
      </section>
    </AppShell>
  );
}
