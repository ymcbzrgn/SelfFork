# ADR-002: SelfFork Mind Architecture (Pillar 3)

- **Status:** Approved (Augmented by ADR-009 §1-§5, 2026-05-23 — dual-pool scoping + group_id primitive + Auto Dream trigger)
- **Date:** 2026-05-07
- **Supersedes:** —
- **Superseded-by:** —
- **Augmented-by:** [`ADR-009_DualPool_Memory_Scoping.md`](./ADR-009_DualPool_Memory_Scoping.md)
- **Companion memory:** `project_yamac_jr_is_user_simulator.md`, `feedback_infra_before_finetune.md`, `feedback_brand_is_selffork_not_personal_name.md`

---

## Context

SelfFork's CLAUDE.md describes Pillar 3 as **"persistent cross-session memory + GraphRAG over codebase + sessions + deterministic context compaction"**. ADR-001 locked the orchestrator MVP without specifying Mind internals. This ADR locks the Mind architecture before `packages/mind/` implementation begins.

Five parallel research agents covered:

1. **Local corpus** (`examples_crucial/`): Letta (3-tier), mem0 (flat ADD-only), Cognee (graph ECL), git-context-controller (pointer-table).
2. **Commercial 2025-2026 standard**: Anthropic Memory Tool + Auto Dream, Claude Code CLAUDE.md/MEMORY.md, OpenAI Codex memories, ChatGPT Memory Sources, Cursor Memories (deprecated cautionary tale), VS Code/Copilot 3-scope, Replit replit.md, AGENTS.md cross-tool standard.
3. **Multi-hop reasoning**: HippoRAG 2 (ICML 2025), Graphiti (bi-temporal), MS GraphRAG (heavy, deprecated for personal AI), LightRAG (debiased eval shows weakness), A-Mem zettelkasten, RAPTOR, AriGraph, PersonalAI hyper-edges.
4. **Eval benchmarks**: LongMemEval (5-axis), MemoryAgentBench (4-axis, ICLR 2026), LoCoMo (persona+temporal-event-graph), PerLTQA (validates Tulving split), HELMET, RULER, Context Rot, BABILong, Evo-Memory, Hindsight 20/20.
5. **Cognitive science**: Tulving 1972 (episodic/semantic), Anderson 1983 ACT-R (procedural), Squire 2004 (declarative/non-declarative), Schacter 1996 (constructive memory), McClelland 1995 Complementary Learning Systems (hippocampus/neocortex/replay), Diekelmann & Born 2010 (selective sleep consolidation), Ebbinghaus 1885 (forgetting curve), Bjork desirable difficulties, SM-2 spaced repetition.

**Key consensus across all five vectors:**

- **Memory is a vector, not a scalar.** HELMET, MemoryAgentBench, LongMemEval all report multi-axis. Single-score memory eval is deprecated 2026.
- **Plain-markdown user-editable surface is a 2026 default.** Cursor Memories (1.0 → 2.1 removal, Nov 2025) proved sidecar passive extraction without user-edit surface fails. Anthropic CLAUDE.md, AGENTS.md (60k+ repos, Linux Foundation governance), VS Code memory all converged on transparent markdown.
- **Tier separation is biologically inevitable.** PerLTQA empirically validates Tulving's split (best performance requires BOTH episodic + semantic retrieval). Squire 2004 establishes at least four declarative/non-declarative subsystems.
- **MS GraphRAG (heavy, 326k tokens/query) is deprecated for personal AI.** HippoRAG 2 (~1000 tokens/query, ICML 2025) + Graphiti (bi-temporal, Apache-2.0, Kuzu-embedded, Ollama-native) is the production-grade lightweight pattern.
- **McClelland 1995 CLS gives direct theoretical backing for the SelfFork three-pillar pipeline:** Hippocampus ↔ Mind (fast episodic), Neocortex ↔ Reflex (slow distilled adapter), Sleep replay ↔ training-data generation from Mind's procedural tier.

---

## Decision

### 1. Six-tier cognitive memory architecture

| Tier | Role | Backend | Write trigger |
|---|---|---|---|
| **T1 Working** | In-context block (persona + active project + current task) | Pydantic in-memory | Manual + per-round |
| **T2 Episodic** | Per-session events (rounds, tool calls, sentinels) | LanceDB vector + DuckDB metadata | Per-round (auto) |
| **T3 Semantic Graph** | Cross-session facts with causality + temporal validity | Kuzu embedded graph (HippoRAG 2 + Graphiti pattern) | Consolidation + structured-source bypass |
| **T4 Procedural** | Operator-style reflex patterns (tool sequences, code style, debug routines) | DuckDB + LanceDB | Consolidation pipeline (deterministic distillation) |
| **T5 Reflection** | Higher-level insights ("lessons learned" from sessions) | DuckDB + LanceDB | Periodic LLM reflection cycle (opt-in) |
| **T6 Recall** | Full audit JSONL transcript (immutable, append-only) | Filesystem (already exists) | Audit logger (already wired) |

**Why six and not three (Letta) or one (mem0):**
- T2 vs T3 split = single-hop (vector) vs multi-hop (graph) routing — adaptive retrieval beats one-size-fits-all (arXiv 2502.11371).
- T4 Procedural is the **fine-tune corpus** (Pillar 1 dataset auto-builds here).
- T5 Reflection separates raw observations from synthesized lessons (Generative Agents UIST 2023 + Hindsight 20/20 2025).
- T6 Recall is read-only derivative — the audit log already exists; no duplication.

### 2. Storage stack (Apache 2.0 throughout)

- **DuckDB** (Apache 2.0) — relational + filter DSL evaluation + analytics. Single-file embedded.
- **LanceDB** (Apache 2.0) — vector-native + time-travel built-in. Arrow-based, single-process embedded.
- **Kuzu** (MIT) — embedded graph store, Graphiti-compatible.

Per-project layout: `~/.selffork/projects/<slug>/mind/{notes.duckdb, vectors.lance/, graph.kuzu/}`.

**Pluggable abstraction layer (Letta `EmbeddingConfig` pattern):** future PostgreSQL/pgvector + Neo4j migration is a config swap, not a rewrite. Day-1 contract via `MindStore` Protocol.

### 3. Embedding (pluggable, BGE-M3 default)

`EmbeddingProvider` Protocol with six implementations:

- **BGE-M3** (default, MIT) — multilingual (English + Turkish + 100+), 1024-dim, single model dense+sparse+ColBERT hybrid output. Local sentence-transformers.
- **OpenAI text-embedding-3-{small,large}** (opt-in) — best quality but API + telemetry.
- **Gemini text-embedding-004** (opt-in) — Google AI Studio API, 768-dim, multilingual.
- **Jina embeddings-v3** (opt-in) — Jina AI API, 1024-dim, multilingual, supports task-specific encoding.
- **Gemma-derived** (opt-in, experimental) — Reflex model embedding head; quality unproven for Q4_0.
- **Ollama** (opt-in) — local serve, `nomic-embed-text` / arbitrary local model.

Per-project override via `selffork.yaml`.

### 3b. Reranking (pluggable, BGE-reranker-v2-m3 default)

`RerankerProvider` Protocol with four implementations. Reranking is a separate stage in the retrieval pipeline (§5) — it sits between candidate retrieval and final selection, and dramatically improves precision on Multi-hop / temporal / domain-specific queries.

- **BGE-reranker-v2-m3** (default, MIT) — multilingual cross-encoder, local sentence-transformers.
- **Jina rerank-v2-base-multilingual** (opt-in) — Jina AI API.
- **Cohere rerank-multilingual-v3.0** (opt-in) — Cohere API.
- **Voyage rerank-2** (opt-in) — Voyage AI API.

The `RetrieveConfig` carries an optional `reranker` field; when set, the retriever fetches `top_k * 4` candidates from vector/graph/hybrid stage and reranks down to the requested `top_k`.

### 4. Compaction — four-layer "forgetting curve" (Ebbinghaus 1885 + DL replay)

| Layer | Strategy | LLM? | Default |
|---|---|---|---|
| **L1 Recency-decay** | `score = recency × tag_priority × manual_pin` (Generative Agents formula) | ❌ | Always on, per-query |
| **L2 Importance distillation** | Pattern matching → "decision sentinels" extracted Episodic→Procedural | ❌ | Consolidation cycle |
| **L3 Semantic clustering** | k-means/DBSCAN; Archival cluster medoid kept, outliers TTL'd | ❌ | Background daily |
| **L4 LLM-summary (opt-in)** | `selffork mind compact --strategy llm --tier archival` | ✓ | Manual only |

**Memory replay** (DL rehearsal): periodic background task refreshes importance scores. Frequently recalled → score rises; never recalled → falls. Provides Pillar 1 fine-tune signal — high-importance procedural patterns become spaced-repetition training items (Bjork desirable difficulties + SM-2 E-Factor).

### 5. Multi-strategy retrieval (Hindsight 20/20 multi-strategy + adaptive routing)

- **Vector** (default for single-hop): LanceDB hybrid (semantic + BM25 + tag filter), top-k + threshold.
- **Graph** (multi-hop / temporal / causality): Kuzu Personalized PageRank (HippoRAG 2 pattern) over passage + phrase nodes joined by `contains` edges.
- **Adaptive router**: query classifier picks vector vs graph vs hybrid based on detected query type (single-fact vs multi-hop vs temporal).
- **Deterministic bypass** (Cognee): structured sources (audit JSONL, decision JSON, kanban events) write triples 1:1 without LLM extraction.

### 6. Bi-temporal facts (Graphiti pattern)

Each Semantic-tier fact carries `valid_from` + `valid_until`. Facts are never mutated; they are superseded. Maps directly to "eski karar superseded by yeni karar" workflow already established in `docs/decisions/`.

### 7. Plain-markdown projection (Anthropic / AGENTS.md / Cursor lesson)

DuckDB + LanceDB + Kuzu are the **internal store**. Alongside, `MEMORY.md` + topic files are emitted under `~/.selffork/projects/<slug>/mind/markdown/` as a **user-editable projection**. The operator can read, edit, delete via filesystem; changes propagate back to internal store on next save.

**Why this matters:** Cursor 2.1 (Nov 2025) removed Memories specifically because users rejected sidecar passive extraction. SelfFork's "ASLA MOCK YOK" + Cursor lesson together mandate plain-markdown transparency.

### 8. Memory provenance / Sources (ChatGPT Memory Sources May 2026)

Every Mind-injected memory carries a provenance trace shown in the UI: "this answer used note X from session S, project P, dated D." `apps/web` `CardDetailPanel` Logs tab will surface this once T2/T3 are wired.

### 9. Path-scoped attachment (Cursor `paths:` glob pattern)

Notes carry frontmatter:
```yaml
paths: ["src/api/**/*.ts", "packages/mind/**/*.py"]
alwaysApply: false
```

Memory injects into context only when the operator is reading a matching file. Saves 128K context budget.

### 10. Async two-model consolidation pipeline (OpenAI Codex pattern)

- **Extract phase** (cheap): Gemma 4 E2B-it (Reflex model itself) extracts decision sentinels from rounds. Per-session, per-round.
- **Consolidate phase** (heavy): a larger model (configurable — could be the operator's claude-code subscription, opencode'in routed Claude/GPT/etc.) runs the periodic reflection cycle on accumulated extractions.
- **Gating**: skip when `agent.rate_limited` (already tracked). Auto-secret-redaction (Codex pattern).

### 11. Sleep-inspired consolidation (Anthropic Auto Dream + Diekelmann & Born 2010)

Four-phase pipeline triggered when ≥24h elapsed AND ≥5 sessions accumulated:

1. **Orientation** — what changed?
2. **Gather Signal** — pattern matching across recent Episodic.
3. **Consolidation** — Episodic → Procedural transfer (deterministic distillation, L2 above).
4. **Prune & Index** — Ebbinghaus decay + medoid clustering.

Selective (future-relevant), not uniform — matches Diekelmann & Born 2010 finding that sleep preferentially consolidates future-relevant traces.

### 12. Eval suite (`packages/mind/eval/`)

Mind quality reported as a **vector** across:

- **LongMemEval 5 axes**: extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention.
- **MemoryAgentBench 4 axes**: Accurate Retrieval, Test-Time Learning, Long-Range Understanding, Conflict Resolution.
- **PerLTQA**: episodic + semantic split validation.
- **LoCoMo**: persona + temporal-event-graph corpus shape.
- **`benchmarks/operator_session_holdouts/`**: SelfFork-specific held-out corpus, questions authored OFFLINE before model sees corresponding sessions.

NIAH + RULER + ∞Bench run as **smoke tests only**, never as headline scores (HELMET 2025 proved synthetic NIAH does not predict downstream).

### 13. AGENTS.md publishing

SelfFork repo root publishes `AGENTS.md` so external tools (Codex, Cursor, opencode, Claude Code via @import) can consume the same operator instructions. Joins the 60k+ repo Linux Foundation cross-tool ecosystem.

---

## Naming convention (locked, fork-friendly)

- **Brand**: "SelfFork" (GitHub, packages, CLI command, dashboard, tool sentinel).
- **User references in code/ADRs/eval/schema**: GENERIC — `operator`, `user`, `owner`, `principal`. **Never** the original creator's personal name.
- **Memory tier names**: `working / episodic / semantic / procedural / reflection / recall`.
- **Eval datasets**: `operator_holdout`, never `<personal-name>_holdout`.
- **Internal Jr name**: "SelfFork Jr" (already locked from 2026-04-30 cleanup).
- **CLAUDE.md / GEMINI.md** can address the assistant as the original author's partner — those files are author-facing. **Everything else is generic.**

See `feedback_brand_is_selffork_not_personal_name.md`.

---

## Three-pillar integration (Complementary Learning Systems theory)

McClelland, McNaughton & O'Reilly 1995 gives direct biological backing:

- **Pillar 3 (Mind) ≡ Hippocampus**: sparse, pattern-separated, fast episodic encoding (T2 + T3).
- **Pillar 1 (Reflex) ≡ Neocortex**: distributed, gradual, slow consolidation extracting latent structure (the fine-tune adapter).
- **Sleep replay ≡ Mind T4 Procedural → Reflex training corpus**: scheduled with Bjork desirable difficulties (spacing + interleaving + retrieval practice) and SM-2-style item difficulty (operator correction frequency as E-Factor).

This makes the three pillars **biologically coherent**, not three independent stacks. T4 Procedural builds the Reflex training set automatically as the operator works; fine-tune time arrives with the dataset already prepared.

For Pillar 2 (Body), the Mind contract is: Body writes session events to T2 Episodic; Mind exposes a `BodyContext` retriever that returns relevant Procedural patterns when Body needs to decide on a UI action.

---

## Implementation order (no MVP iteration; each tier ships production-quality on landing)

Per `feedback_no_mvp_full_quality_first_time.md`: scope can be small, quality cannot be staged. Tiers land **one at a time, each fully production-quality** — pluggable interfaces, eval coverage, plain-markdown projection, provenance traces, AGENTS.md alignment all included on first commit. No "MVP version" anywhere.

Order is dictated by dependency graph (lower tiers serve higher), not by feature truncation:

| Order | Tier(s) landing | What ships fully on landing |
|---|---|---|
| **1** | Storage stack + abstractions | `MindStore` Protocol, DuckDB+LanceDB+Kuzu pluggable backends, `EmbeddingProvider` Protocol with all 4 implementations (BGE-M3 default), filter DSL, tag junction, bi-temporal schema, plain-md projection writer, provenance recorder. Full eval harness scaffolding. AGENTS.md published. |
| **2** | T6 Recall + T2 Episodic | Audit-derived T6 read API; T2 Episodic per-round writer with deterministic bypass for structured sources, hybrid (semantic + BM25 + tag) retriever with adaptive routing, path-scoped glob attachment, `selffork mind` CLI surface, `mind_recall` + `mind_note_add` tools. LongMemEval extraction-axis + abstention-axis eval green. |
| **3** | T1 Working + T4 Procedural + Compaction L1-L3 | Letta-style in-context block, Procedural pattern-matching distillation (L2), Ebbinghaus + medoid clustering (L3), recency-decay scoring (L1), memory replay importance refresh. LongMemEval knowledge-updates-axis + MemoryAgentBench Test-Time Learning axis green. |
| **4** | T3 Semantic Graph | Kuzu graph store, HippoRAG 2 PPR (passage + phrase + contains-edges), Graphiti bi-temporal facts (`valid_from` + `valid_until`), async two-model consolidation pipeline, structured-source deterministic bypass producing triples 1:1. LongMemEval multi-session + temporal axes green; MemoryAgentBench Conflict Resolution axis green. |
| **5** | T5 Reflection + Compaction L4 | Generative-Agents reflection-of-reflection cascade, Anthropic Auto Dream 4-phase (Orientation → Gather Signal → Consolidation → Prune & Index), opt-in LLM-summary compaction. PerLTQA cognitive-validity eval green. Provenance UI surfaces in `apps/web` `CardDetailPanel` Logs/Tools tabs. |
| **6** | Three-pillar bridge | Reflex training schedule (artificial sleep cycle): selective replay of T4 Procedural with Bjork desirable difficulties (spacing + interleaving + retrieval practice) and SM-2 E-Factor (operator correction frequency). LoCoMo persona+temporal-event-graph corpus shape; full operator-grounded held-out eval suite. Pillar 1 (Reflex) connects. |

**Each order milestone is a feature-complete production landing.** No tier is "stub now, fill later." If T2 lands, its retriever is the production retriever — not a placeholder. If T3 lands, HippoRAG 2 PPR is wired end-to-end with eval, provenance, projection — not a partial graph implementation pending v0.2.

---

## Alternatives considered

- **Letta 3-tier verbatim**: Insufficient — no Procedural tier (no fine-tune corpus auto-build); LLM-controlled memory editing conflicts with `project_yamac_jr_is_user_simulator.md` (Jr is USER simulator, not memory maintainer); LLM-driven default compaction conflicts with `feedback_infra_before_finetune.md`.
- **mem0 flat with classifier**: Insufficient — no in-context vs searchable separation; cloud-first telemetry as core dep.
- **Cognee batch ECL**: Heavy; LLM-required for entity extraction; ontology bootstrap overhead.
- **GCC pointer-only**: Too thin — no semantic / procedural retrieval, only timeline.
- **MS GraphRAG**: 326k tokens/query and 281 minutes for 1M tokens — DOA for personal AI.
- **Single-tier vector (mem0 v3 ADD-only)**: Loses multi-hop reasoning capability; fails MemoryAgentBench Conflict Resolution axis.

The chosen six-tier + multi-strategy retrieval + plain-md projection synthesizes the best of each while rejecting the anti-patterns.

---

## Consequences

### Positive
- **Three-pillar biological coherence**: Mind directly feeds Reflex via Sleep replay analogy.
- **Pluggable storage day 1** (Letta `EmbeddingConfig` pattern) — future PostgreSQL/Neo4j migration is config-only.
- **Operator trust**: plain-markdown projection + provenance UI; no opacity-induced revolt (Cursor 2.1 lesson avoided).
- **Vector eval reporting**: never overclaim memory quality.
- **Cross-tool ecosystem fit**: AGENTS.md publish.
- **Apache 2.0 / MIT throughout**: no license lock-in.

### Negative / Risks
- **Surface area is large** (six tiers × multiple subsystems). Mitigated by phasing — MVP keeps it to four tiers.
- **Three separate stores (DuckDB + LanceDB + Kuzu)**: deployment complexity vs single-DB simplicity. Mitigated by all three being embedded single-process.
- **HippoRAG 2 / Graphiti are recent (2024-2025)**: less production-tested than Letta. Mitigated by Graphiti being Apache-2.0 production-deployed at Zep.
- **Eval suite construction effort**: held-out corpus authoring is real work. Mitigated by bootstrapping with LongMemEval-S corpus, augmenting with operator-grounded questions over time.

### Backward compatibility
- No prior Mind exists; this is a greenfield decision. No migration.
- The audit JSONL (Pillar 1 of orchestrator infra) is reused as T6 Recall — read-only derivative.

---

## References

### Local corpus
- `examples_crucial/letta/` — 3-tier (Block / Passage / Message), `services/passage_manager.py:43`, `schemas/memory.py:68`, `services/summarizer/summarizer.py` (rejected default).
- `examples_crucial/mem0/` — flat ADD-only v3, `mem0/memory/main.py:799` (hash dedup), `1343-1499` (multi-signal scoring + spread-attenuation).
- `examples_crucial/cognee/` — ECL pipeline, `cognee/api/v1/cognify/cognify.py:310-336`, `infrastructure/engine/models/DataPoint.py:104-131` (UUID5 + Annotated `_Embeddable()`).
- `examples_crucial/git-context-controller/` — pointer-table SSOT, tiered query gradient (`scripts/gcc_commit.sh:84-89`).

### Papers
- Tulving, E. (1972). *Organization of Memory* — episodic vs semantic.
- Anderson, J. R. (1983). *The Architecture of Cognition* — ACT-R, knowledge compilation.
- Squire, L. R. (2004). Memory systems of the brain. *Neurobiology of Learning and Memory*, 82(3).
- Schacter, D. L. (1996). *Searching for Memory*.
- McClelland, McNaughton & O'Reilly (1995). Why there are complementary learning systems. *Psychological Review*, 102(3).
- Diekelmann & Born (2010). The memory function of sleep. *Nature Reviews Neuroscience*, 11.
- Ebbinghaus, H. (1885). *Über das Gedächtnis*.
- Bjork & Bjork (2011). Making things hard on yourself, but in a good way: creating desirable difficulties.
- Wozniak (1987). SM-2 algorithm.
- Park et al. (2023). Generative Agents — UIST 2023, arXiv:2304.03442.
- Packer et al. (2023). MemGPT, arXiv:2310.08560.
- Gutiérrez et al. (2024). HippoRAG, NeurIPS 2024, arXiv:2405.14831.
- Jiménez Gutiérrez et al. (2025). HippoRAG 2 / "From RAG to Memory", ICML 2025, arXiv:2502.14802.
- Rasmussen et al. (2025). Zep / Graphiti, arXiv:2501.13956.
- Edge et al. (2024). Microsoft GraphRAG, arXiv:2404.16130.
- Guo et al. (2024). LightRAG, EMNLP 2025, arXiv:2410.05779.
- Chhikara et al. (2025). Mem0, arXiv:2504.19413.
- Sarthi et al. (2024). RAPTOR, ICLR 2024, arXiv:2401.18059.
- Xu et al. (2025). A-Mem, NeurIPS 2025, arXiv:2502.12110.
- Zhong et al. (2024). MemoryBank, AAAI 2024, arXiv:2305.10250.
- Wu et al. (2025). LongMemEval, ICLR 2025, arXiv:2410.10813.
- Hu, Wang, McAuley (2026). MemoryAgentBench, ICLR 2026, arXiv:2507.05257.
- Maharana et al. (2024). LoCoMo, ACL 2024, arXiv:2402.17753.
- Du et al. (2024). PerLTQA, SIGHAN-10, arXiv:2402.16288.
- Yen et al. (2025). HELMET, ICLR 2025, arXiv:2410.02694.
- Hsieh et al. (2024). RULER, COLM 2024, arXiv:2404.06654.
- Hong et al. (2025). Context Rot. Chroma Research.
- Latimer et al. (2025). Hindsight is 20/20, arXiv:2512.12818.

### Industry / commercial
- Anthropic Memory Tool (2025-09-29 launch): https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- Anthropic Auto Dream (2026-05-06 research preview): https://claudefa.st/blog/guide/mechanics/auto-dream
- Claude Code Memory: https://code.claude.com/docs/en/memory
- OpenAI Codex Memories: https://developers.openai.com/codex/memories
- ChatGPT Memory Sources (2026-05): https://releasebot.io/updates/openai/chatgpt
- Cursor 1.0 launch / 2.1.20 removal: https://cursor.com/changelog/1-0, https://forum.cursor.com/t/custom-modes-and-memories-gone-in-2-1/143744
- VS Code Copilot agents memory: https://code.visualstudio.com/docs/copilot/agents/memory
- AGENTS.md cross-tool standard: https://agents.md/, donated to Linux Foundation 2025-12-09.
- Mem0 State of AI Agent Memory 2026: https://mem0.ai/blog/state-of-ai-agent-memory-2026
- Graphiti Knowledge Graph Memory (Neo4j blog): https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/
