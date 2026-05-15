/**
 * Recall query bar — Order 9.
 *
 * Minimal form: free-text query + tier filter. Submits to
 * ``POST /api/projects/<slug>/mind/recall`` and surfaces the hits
 * inline so the operator never leaves the Context tab.
 */
"use client";

import { useState } from "react";

import {
  recallMind,
  type NoteResponse,
} from "@/lib/api";
import { useCockpitStore, type MindTier } from "@/lib/store";

import { NoteList } from "./NoteList";

const TIERS: MindTier[] = [
  "working",
  "episodic",
  "semantic_graph",
  "procedural",
  "reflection",
  "recall",
];

export function RecallQueryBar({ slug }: { slug: string }) {
  const query = useCockpitStore((s) => s.contextRecallQuery);
  const setQuery = useCockpitStore((s) => s.setContextRecallQuery);
  const tier = useCockpitStore((s) => s.contextRecallTier);
  const setTier = useCockpitStore((s) => s.setContextRecallTier);

  const [hits, setHits] = useState<NoteResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async () => {
    if (!query.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      const result = await recallMind(slug, {
        query,
        tier: tier ?? undefined,
        top_k: 20,
      });
      setHits(result.hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-card/40 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <input
          type="search"
          placeholder="Recall query…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void submit();
          }}
          className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm"
          data-testid="recall-input"
        />
        <label className="flex items-center gap-1">
          <span className="text-muted-foreground">Tier</span>
          <select
            aria-label="Recall tier"
            value={tier ?? ""}
            onChange={(e) =>
              setTier((e.target.value as MindTier | "") || null)
            }
            className="rounded-md border border-border bg-card px-2 py-1 font-mono text-[11px]"
          >
            <option value="">all</option>
            {TIERS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={pending || !query.trim()}
          className="rounded-md bg-primary px-3 py-1 text-sm font-medium text-primary-foreground disabled:opacity-40"
          data-testid="recall-submit"
        >
          Recall
        </button>
      </div>
      {error ? (
        <p className="text-xs text-rose-300">Error: {error}</p>
      ) : null}
      {hits.length > 0 ? (
        <div className="mt-2">
          <p className="mb-2 text-xs text-muted-foreground">
            {hits.length} hits
          </p>
          <NoteList notes={hits} />
        </div>
      ) : null}
    </div>
  );
}
