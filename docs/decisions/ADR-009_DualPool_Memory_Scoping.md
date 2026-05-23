# ADR-009 — Dual-Pool Memory Scoping: PROJECT + GLOBAL Havuzlar, group_id Primitive ve Auto Dream Tetikleyici

## Status

- **Status:** Approved — operatör 2026-05-23 onayı (4 AskUserQuestion'da hepsinin "Recommended" seçimi).
- **Type:** Architecture ADR — Mind pillar (Pillar 3) genişletmesi. ADR-002'yi YERINE GEÇMEZ; **augment** eder.
- **Date:** 2026-05-23
- **Builds on:**
  - [`ADR-002_Mind_Architecture.md`](./ADR-002_Mind_Architecture.md) — DOMINANT. 6-tier mimari, storage stack (DuckDB + LanceDB + Kuzu), pluggable provider'lar, plain-md projection, eval suite SSOT.
  - [`ADR-008_Autonomy_Heartbeat.md`](./ADR-008_Autonomy_Heartbeat.md) — Heartbeat outer loop; §3-§5 perceive→decide→act→record; audit.jsonl T2 Episodic feed kaynağı.
- **Related:**
  - ADR-006 §7 self-host felsefesi (cloud-bound runtime YASAK).
  - ADR-007 §4 S-Memory sprint blok'u (Faz H'de yazılır).
  - `[[s-memory-scope-2026-05-23]]` operatör direktifi (verbatim: "proje bazlı VE ayrıca ortak genel memory havuzunu yaratıcaz").
  - `[[hivemind-adoption-2026-05-22]]` (5 pattern lift; inspiration-only verdict).
- **Supersedes:** —
- **Superseded-by:** —

---

## Context

`docs/decisions/ADR-002_Mind_Architecture.md` (Approved 2026-05-07) **6-tier cognitive memory architecture** (T1 Working / T2 Episodic / T3 Semantic Graph / T4 Procedural / T5 Reflection / T6 Recall) için **per-project storage layout** sabitler:

```
~/.selffork/projects/<slug>/mind/
  notes.duckdb
  vectors.lance/
  graph.kuzu/
```

**Boşluk:** ADR-002 cross-project / global / operator-identity havuzu **explicit yazmaz**. Her şey proje sınırı içinde yaşar.

**Operatör direktifi (2026-05-23 00:11 GMT+3, verbatim):**

> *"hivemind sadece örnekti başka açık kaynakları da araştırıcaz sonra ve en iyi proje bazlı ve ayrıca ortak genel memory havuzunu yaratıcaz!"*

İki kelime kritik: **"başka açık kaynakları da araştırıcaz"** (Hivemind yetersiz) ve **"proje bazlı VE ayrıca ortak genel"** (iki ortogonal pool).

**Self Jr "uyumayan ikinci ben" vizyonu** (ADR-008 §1) için:
- **PROJECT pool** — operatörün **bir proje üstünde** yaptığı her şey: kararlar, oturumlar, kanban, kod stili, debug refleksleri.
- **GLOBAL pool** — operatörün **kim olduğu**: cross-project tercihler, identity, "her zaman böyle davran" refleksleri, ne severim ne sevmem, ortak skills, projeler arası lessons learned.

İkisi olmadan Self Jr ya "her sabah yeniden tanış" durumunda olur (PROJECT-only) ya da "proje bağlamını unutuyor" durumunda (GLOBAL-only).

---

## Faz A — 5 paralel kaynak araştırması (2026-05-23)

S-Memory sprint Faz A'da paralel 5 selffork-researcher + 1 explorer-god 6 ajan dispatch:

| Aday | Lisans | Self-host | 6-tier mapping | Dual-pool desteği | Pattern lift |
|---|---|---|---|---|---|
| **Letta v1 (Ekim 2025)** | Apache 2.0 | Evet | Block/Passage/Message (3-tier, dar) | **BlocksAgents m2m + attach_block** ✅ doğrudan emsal | sleep-time agent turn-counter gate, EmbeddingConfig Literal swap, 0.9× context trigger, 3-stage summarizer fallback |
| **mem0 v3 (ADD-only, 2026-05)** | Apache 2.0 | Kısmi (PostHog telemetri default ON; opt-out var) | Flat ADD-only (T2 zayıf) | **YOK** — flat `(user_id, agent_id, run_id)` AND-combined | MD5 hash dedup, sigmoid BM25 normalization, adaptive `max_possible` divisor, entity-boost specificity damping |
| **cognee (MIT)** | MIT | Evet (Ollama-native) | Graph-RAG (T3 ağırlıklı) | Pool A (`Dataset` per-project), Pool B YOK | Pluggable `calculate_chunk_graphs` callback, UUID5 + Annotated `Embeddable/Dedup/LLMContext` markers, deterministic bypass for structured sources |
| **Anthropic Memory Tool (2025-09-29)** | Anthropic API | Client-side (operator backend); cloud-bound DEĞİL | Tool surface `view/create/str_replace/insert/delete/rename` | Tek `/memories` directory; pool ayrımı client-side application | `BetaAbstractMemoryTool` pluggable backend ABC |
| **Anthropic Auto Dream (2026-05-06)** | spec (claudefa.st 3rd party), MIT (dream-skill replikasyon) | Evet | T5 Reflection spec | n/a | **4-phase pipeline** (Orientation → Gather Signal → Consolidation → Prune & Index), trigger ≥24h+≥5 sessions, grep-style scan, 200-line MEMORY.md index |
| **Claude Code CLAUDE.md hierarchy** | Anthropic docs | Evet (filesystem-based) | n/a | **EVET — managed → user (global) → project → local concatenated** ✅ doğrudan dual-pool emsal | Load order + `MEMORY.md` 200-line index + path-scoped `.claude/rules/` + on-demand topic files |
| **Graphiti (Apache 2.0, Zep)** | Apache 2.0 | Evet (Kuzu embedded) | T3 bi-temporal (4-axis: valid_at/invalid_at/expired_at/reference_time) | **`group_id: str` per edge + `group_ids: list[str]` query** ✅ DUAL-POOL PRIMITIVE | bi-temporal schema, implicit supersede via temporal overlap, Kuzu embedded driver shape, model_size + semaphore_gather |
| **Hivemind (Apache 2.0, activeloopai)** | Apache 2.0 | Hayır (cloud-bound Activeloop SaaS) | 3-table flat (memory/sessions/skills) | **Flat workspace abstraction** (project vs global YOK) | 6 lifecycle hook shape, skillify gate (host-CLI reuse), AGENTS.md BEGIN/END idempotent marker, symlink fan-out, 402 silent-failure banner |
| **mcp-memory-service (doobidoo)** | Apache 2.0 | Evet | n/a | Tag-based (`X-Agent-ID`) — partial | autonomous consolidation, temporal contradiction detection — Auto Dream community emsal |
| **claude-mem (thedotmack)** | (NEEDS VERIFICATION) | Evet (SQLite + Chroma + port 37777) | Per-project | Per-project (global YOK) | **Çakışma riski** — SelfFork own namespace `~/.selffork/global/` ayrı olmalı |

**Karşılaştırmadan çıkan kararlar:**

1. **group_id Graphiti'den lift** — schema-native partition, production-tested, `group_ids=["p:foo", "g:global"]` cross-pool query out-of-the-box.
2. **Filesystem dual-layout Claude Code'dan emsal** — `~/.selffork/global/mind/` vs `~/.selffork/projects/<slug>/mind/` concatenated load order, override DEĞİL.
3. **Auto Dream Anthropic'ten verbatim spec** — 4-phase + 24h+5-sessions trigger.
4. **Heartbeat audit.jsonl → T2 ingest** — S-Auto'nun zaten yazdığı feed.
5. **Identity için T7 yeni tier YOK** — operatör direktifi "ortak genel havuz" der, "identity tier" demez; T4 GLOBAL + T5 GLOBAL stratum yeter.
6. **Hivemind verdict aynı** — inspiration-only, 5 pattern lift; runtime dep yok.

---

## Decision

### 1. PoolScope primitive (`group_id` field) — Graphiti emsali

`packages/mind/src/selffork_mind/store/base.py` `StoreScope` Pydantic model **`group_id` field**'i alır:

```python
@dataclass(frozen=True, slots=True)
class StoreScope:
    project_slug: str | None = None      # mevcut alan (ADR-002 Order 1)
    group_id: str | None = None           # YENİ — "p:<slug>" veya "g:global"
    tier: str | None = None
    tags: tuple[str, ...] = ()
    # ... existing fields ...

@dataclass(frozen=True, slots=True)
class PoolScope:
    """Cross-pool retrieval boundary; passed to MindStore.retrieve(...)."""
    project_slug: str | None = None
    include_global: bool = False
    # When include_global=True and project_slug set:
    #   group_ids = ["p:<slug>", "g:global"]
    # When only project_slug:
    #   group_ids = ["p:<slug>"]
    # When only include_global:
    #   group_ids = ["g:global"]
```

**SQL semantics (DuckDB):**

```sql
SELECT * FROM notes
WHERE group_id IN ($group_ids_list)
  AND (valid_from IS NULL OR valid_from <= NOW())
  AND (valid_until IS NULL OR valid_until > NOW());
```

**Backward compatibility:** Mevcut `project_slug` alanı korunur. Yeni `group_id` write-trigger'da `project_slug` → `group_id = f"p:{project_slug}"` auto-derive edilir. Migration aşaması yok; mevcut PROJECT verisi `group_id` field'ı boş bırakılır ve query layer'da `coalesce(group_id, "p:" || project_slug)` ile çözülür.

### 2. Filesystem layout — PROJECT + GLOBAL physical separation

```
~/.selffork/
├── projects/
│   └── <slug>/
│       ├── kanban.json
│       ├── audit/            # T6 Recall read-only source
│       └── mind/             # PROJECT pool
│           ├── notes.duckdb       group_id=p:<slug>
│           ├── vectors.lance/     group_id=p:<slug>
│           ├── graph.kuzu/        group_id=p:<slug>
│           ├── markdown/          # plain-md projection (§7 ADR-002)
│           └── provenance.jsonl   # JSONL append (§8 ADR-002)
│
└── global/                   # YENİ — GLOBAL pool
    └── mind/
        ├── notes.duckdb       group_id=g:global
        ├── vectors.lance/     group_id=g:global
        ├── graph.kuzu/        group_id=g:global
        ├── reflection/        # T5 reflection MD topic files
        ├── markdown/          # operator-style identity MD projection
        └── provenance.jsonl
```

**Two physical DBs, one query interface.** Cross-pool query `MindStore.retrieve(scope=PoolScope(project_slug="foo", include_global=True))` iki engine'a paralel `asyncio.gather(...)` ile vuruyor; sonuçlar `rerank()` ile birleştirilir.

**Reasoning (Graphiti vs single-DB tradeoff):**
- Tek DB + group_id partition Graphiti default; ama proje silinince global ile karışık silme riski.
- İki physical DB + group_id partition = belt-and-suspenders. Filesystem-level proje silmek global'i bozmaz.
- Cross-pool query latency 2× engine roundtrip; ama operator çok-proje senaryosunda da sabit kalır (engine başına lokal).

### 3. T-pool mapping matrix

| Tier | Pool | Path | Write-trigger |
|---|---|---|---|
| **T1 Working** | RAM (pool-agnostic) | in-process MutableMapping | per-round (ephemeral) |
| **T2 Episodic** | **PROJECT** | `~/.selffork/projects/<slug>/mind/{notes.duckdb,vectors.lance}` | per-round + Heartbeat audit.jsonl ingest |
| **T3 Semantic Graph** | **PROJECT + GLOBAL** (split by source) | `mind/graph.kuzu/` her iki pool'da | consolidation + structured-source bypass |
| **T4 Procedural** | **PROJECT** (codebase patterns) + **GLOBAL** (operator-style refleks) | her iki pool'da | distillation pipeline |
| **T5 Reflection** | **GLOBAL only** | `~/.selffork/global/mind/reflection/` | Auto Dream periodic |
| **T6 Recall** | **PROJECT only** (read-only audit JSONL) | `~/.selffork/projects/<slug>/audit/` | audit logger (already wired, S3+S-Auto) |

**Identity (T7 yok):**
- Operatör direktifi "ortak genel havuz" der, "identity tier" demez.
- Operatör persona + cross-project preferences **T4 GLOBAL** stratum'unda yaşar (refleks pattern olarak).
- Cross-project lessons learned **T5 GLOBAL** stratum'unda yaşar.
- ADR-002 6-tier sayısı **lock**, T7 eklenmez.

### 4. Auto Dream tetikleyici — Hybrid (Heartbeat idle + threshold)

ADR-002 §11 4-fazlı pipeline (Orientation → Gather Signal → Consolidation → Prune & Index) Heartbeat idle tick'inde **ASLA** doğrudan çalışmaz; threshold gate'inden geçer.

**Tetik sırası (Heartbeat tick içinde):**

```python
async def maybe_run_auto_dream(world_state: WorldState) -> DreamResult | None:
    cp = await load_checkpoint()
    now = datetime.now(timezone.utc)

    # Gate 1: hours_since_last_dream >= 24
    if cp.last_dream_at and (now - cp.last_dream_at) < timedelta(hours=24):
        return None

    # Gate 2: sessions_since_last_dream >= 5
    if cp.sessions_since_last_dream < 5:
        return None

    # Gate 3: not currently rate-limited (ADR-008 quota signal)
    if world_state.rate_limited:
        return None

    # Gate 4: idle (no active task in last 5 min)
    if world_state.recent_activity_within(minutes=5):
        return None

    # All gates passed — run 4-phase pipeline
    return await auto_dream.run_pipeline(world_state)
```

**4-phase pipeline çalıştığında:**
1. **Orientation** — GLOBAL pool + PROJECT pool envanteri (notes.duckdb sayım, son ne yazıldı).
2. **Gather Signal** — grep-style targeted scan: user corrections, explicit saves, recurring themes, decision sentinels. **Exhaustive transcript reading YASAK.**
3. **Consolidation** — relative→absolute date, contradicted facts delete, stale removal, overlapping merge. T2 Episodic → T4 Procedural promotion (deterministic distillation).
4. **Prune & Index** — `MEMORY.md` <200 lines. Stale pointer remove, new link add, contradiction resolve. Ebbinghaus decay + medoid clustering (ADR-002 §4 L1+L3).

**Heartbeat audit kaydı:**
```jsonl
{"tick": 4823, "timestamp": "2026-05-24T03:12:55Z", "trigger": "idle",
 "legal_actions": ["AUTO_DREAM_RUN"], "decision_action": "AUTO_DREAM_RUN",
 "result_summary": {"phase": "Consolidation", "promoted": 7, "pruned": 23,
                    "duration_ms": 14552}, "air_alert": false,
 "idempotency_key": "auto_dream_20260524_031255"}
```

### 5. Heartbeat audit.jsonl → T2 Episodic ingest pipeline

S-Auto Faz E `~/.selffork/heartbeat/audit.jsonl` yazıyor (per tick: `tick`, `timestamp`, `trigger`, `world_state`, `legal_actions`, `decision_*`, `result_*`, `air_alert`, `idempotency_key`).

S-Memory yeni modül: `packages/mind/src/selffork_mind/ingest/heartbeat.py`

```python
class HeartbeatIngester:
    """Tails ~/.selffork/heartbeat/audit.jsonl and feeds T2 Episodic writer."""

    def __init__(
        self,
        audit_path: Path,
        episodic_writer: EpisodicWriter,
        checkpoint_path: Path,
    ): ...

    async def run(self) -> None:
        """Tail-follow audit file; on new entry → episodic_writer.write_round(...)
        with structured-source bypass (no LLM extraction needed)."""
        ...
```

**Bypass logic:** Heartbeat audit kayıtları **structured source** (ADR-002 §5 deterministic bypass kuralı). LLM çağrısı yok; entries doğrudan T2 Episodic'e yazılır. Idempotency_key dedup hash olarak kullanılır (mem0 hash dedup pattern lift).

Heartbeat ingester FastAPI lifespan'da spawn edilir (S3+S-Auto pattern), AsyncTask, on-shutdown gracefully drain.

### 6. Cross-pool query semantics

```python
# Use case 1: Sadece PROJECT pool
hits = await store.retrieve(query="auth bug", scope=PoolScope(project_slug="selffork"))
# SQL: WHERE group_id = "p:selffork"

# Use case 2: PROJECT + GLOBAL (operator daily flow)
hits = await store.retrieve(
    query="how does operator approach state machines",
    scope=PoolScope(project_slug="selffork", include_global=True)
)
# Parallel:
#   project_engine.retrieve(WHERE group_id IN ("p:selffork"))
#   global_engine.retrieve(WHERE group_id IN ("g:global"))
# Merge + rerank (BGE-reranker-v2-m3) → top_k

# Use case 3: Sadece GLOBAL (cross-project identity recall)
hits = await store.retrieve(query="operator likes minimalist UIs",
                             scope=PoolScope(include_global=True))
# SQL: WHERE group_id = "g:global"
```

**Adaptive routing (ADR-002 §5):** Query classifier `include_global=True` default'unu **operator-identity** ve **cross-project** sorularda set eder (heuristic: query contains "ben", "operator", "her zaman", "genelde", "tüm projelerde").

### 7. Migration policy (ADR-002 Order 1-6 production verisi)

Mevcut `~/.selffork/projects/<slug>/mind/` PROJECT verisi (Order 1-3 PRODUCTION) **dokunulmaz**. `group_id` field'ı write-time defaulted, read-time `coalesce(group_id, "p:" || project_slug)`.

**~/.selffork/global/mind/** yeni dizin; ilk Auto Dream run'ında otomatik yaratılır (`mkdir -p` + DDL).

**No data migration.** Existing T2/T3/T4/T6 PROJECT olarak kalır; T5 GLOBAL olarak yeni başlar.

### 8. Plain-markdown projection (§7 ADR-002 dual-pool extension)

ADR-002 §7 plain-md projection PROJECT pool için `~/.selffork/projects/<slug>/mind/markdown/`. ADR-009 GLOBAL pool için `~/.selffork/global/mind/markdown/` ekler:

```
~/.selffork/global/mind/markdown/
├── MEMORY.md              # 200-line index (Auto Dream maintained)
├── operator/
│   ├── preferences.md     # T4 GLOBAL refleksler
│   ├── style.md           # operator code style
│   └── refleksler.md      # cross-project patterns
└── reflection/
    ├── 2026-05-23.md       # T5 daily/weekly reflection topics
    └── lessons.md          # cross-project lessons learned
```

Bidirectional sync: filesystem edit → next save → DuckDB upsert (Cursor 2.1 lesson — operator her zaman görebilir, edit edebilir, silebilir).

### 9. AGENTS.md BEGIN/END idempotent marker (Hivemind H3 lift)

`AGENTS.md` (repo root) + `CLAUDE.md` + `GEMINI.md` + `AGENT.md` (OpenCode) için idempotent insertion:

```
<!-- BEGIN selffork-mind -->
## SelfFork Mind Access

Use `mind_recall(query, scope)` and `mind_note_add(...)` for memory operations.

- PROJECT pool: this project's notes/decisions/codebase patterns
- GLOBAL pool: operator preferences and cross-project lessons

Plain-md projections:
- ~/.selffork/projects/<slug>/mind/markdown/
- ~/.selffork/global/mind/markdown/

Tools: mind_recall (with PoolScope), mind_note_add, mind_compact.
<!-- END selffork-mind -->
```

`packages/mind/src/selffork_mind/publishing/markdown_block.py` Hivemind verbatim lift (`upsertSelffokBlock` / `stripSelffokBlock`).

### 10. Eval suite (§12 ADR-002 dual-pool extension)

LongMemEval / MemoryAgentBench / PerLTQA / LoCoMo eval'leri **per-pool ayrı çalıştırılır**:
- `eval/longmemeval.py --scope=project` — sadece PROJECT pool
- `eval/longmemeval.py --scope=global` — sadece GLOBAL pool
- `eval/longmemeval.py --scope=hybrid` — `include_global=True` cross-pool

Yeni axis: **Cross-pool Recall** — query GLOBAL'de yazıldı, PROJECT pool query'sinde `include_global=True` ile dönüyor mu?

---

## Naming convention (lock)

- **Pool slug formatı:** `p:<project-slug>` PROJECT, `g:global` GLOBAL. Diğer prefix'ler (örn. `publish:<slug>` ADR-002 §13 publishing için) future ADR'de açılır.
- **Path slug:** `~/.selffork/projects/<slug>/` PROJECT, `~/.selffork/global/` GLOBAL. `global` literal; `projects/` plural literal.
- **Generic naming devamı:** operator, user, owner, principal — `[[brand-is-selffork-not-personal-name]]` (ADR-002 ile uyum).

---

## Implementation Order (S-Memory sprint Faz C-G)

| Faz | Modüller | Test odak |
|---|---|---|
| **C** | `store/lance.py` (LanceDB store — ADR-002'de declared, henüz yok), `store/pool.py` (PoolResolver), `store/base.py` patch (`PoolScope` + `group_id`) | Cross-pool isolation, atomic write per engine, lance vector insert |
| **D** | `ingest/heartbeat.py` (audit.jsonl tail → T2), `memory/tiers/working.py` T1 RAM, T2 Episodic global write path | Heartbeat round-trip ingest, T1 ephemeral, T2 LongMemEval extraction+abstention |
| **E** | T6 Recall PROJECT-scope reaffirm, T4 Procedural PROJECT/GLOBAL split, compaction L1+L2 wire | T4 GLOBAL operator refleks, MemoryAgentBench Test-Time Learning |
| **F** | T3 Semantic Graph dual-pool (Kuzu engine per pool), async two-model consolidation wire | LongMemEval multi-session + temporal, Conflict Resolution axis |
| **G** | T5 Reflection GLOBAL, Auto Dream 4-phase pipeline (Orientation → Gather → Consolidation → Prune+Index), Heartbeat tetik gate'leri, compaction L3+L4 | PerLTQA cognitive-validity, Auto Dream end-to-end smoke, idempotency_key dedup |

ADR-002 Order 1 production-quality kaldı; Order 2-6 S-Memory altında **dual-pool extension** ile sonlandırılır. Eksik production-quality maddeler:
- LanceDB store wire (`store/lance.py`)
- Heartbeat audit.jsonl → T2 ingest (`ingest/heartbeat.py`)
- Async two-model graph consolidation LLM path (`graph/consolidation.py:_llm_path`)
- Auto Dream 4-phase pipeline (`reflection/auto_dream.py`)
- Cross-pool query orchestration (`store/pool.py:PoolResolver`)
- MemoryAgentBench Test-Time Learning + PerLTQA + LoCoMo eval (`eval/*`)

---

## Alternatives considered

- **A. Tek DB + group_id partition (Graphiti default).** Avantaj: tek file, basit. Dezavantaj: proje silmek global'i de bozar; backup/restore granularity yok. **REJECT.**

- **B. Ayrı PoolResolver (group_id YOK).** Avantaj: schema değişmez. Dezavantaj: cross-pool query 2× engine roundtrip + merge logic; group_id Graphiti'nin proven dual-pool primitive'i. **REJECT** — group_id primitive lift kazançı yüksek.

- **C. Identity için T7 yeni tier.** Avantaj: identity'ye explicit slot. Dezavantaj: ADR-002 6-tier lock'unu bozar; T4 GLOBAL + T5 GLOBAL zaten karşılayabilir. **REJECT.**

- **D. Pure Heartbeat idle Auto Dream (threshold yok).** Avantaj: basit. Dezavantaj: her idle tick'te çalışırsa token israfı + rate-limit. **REJECT.**

- **E. Ayrı asyncio daemon.** Avantaj: Heartbeat'ten bağımsız. Dezavantaj: ek lifecycle + checkpoint + shutdown koordinasyonu. **REJECT.**

- **F. Manual only Auto Dream (`selffork mind dream`).** Avantaj: en basit. Dezavantaj: "uyumayan ikinci ben" vizyonuna ters. **REJECT.**

- **G. ADR-002 in-place patch.** Avantaj: tek dokümanda toplam. Dezavantaj: Approved ADR'yi modify etmek supersede chain semantic'ini kırar; karar tarihçesi belirsizleşir. **REJECT.**

---

## Consequences

### Positive

- **Operatör direktifi karşılanır** — dual-pool (PROJECT + GLOBAL) explicit, schema-level.
- **Self Jr identity persistence** — cross-project operator-style refleks T4 + T5 GLOBAL'de yaşar.
- **Heartbeat audit → T2 ingest pipeline** — S-Auto'nun çıktısı otomatik Mind feed olur.
- **Graphiti pattern lift** — production-tested group_id primitive; cross-pool query out-of-the-box.
- **Filesystem-level isolation** — backup/restore granularity per-pool; proje silmek global'i bozmaz.
- **ADR-002 immutable** — Approved doc dokunulmadı, supersede chain temiz.
- **Plain-md projection genişler** — GLOBAL pool için de operator editable.
- **Cross-tool standard uyumu** — AGENTS.md BEGIN/END marker tüm CLI'larda idempotent.
- **No new tier** — ADR-002 6-tier lock korunur.

### Negative / Risks

- **Cross-pool query latency** — 2× engine roundtrip. Mitigation: `asyncio.gather()` paralel; per-engine connection pool. Operator beklentisi: hybrid query <500ms.
- **Heartbeat ingester drift** — audit.jsonl yazımı ile T2 ingest arasında lag. Mitigation: idempotency_key dedup + tail-follow + checkpoint.
- **GLOBAL pool corruption riski** — tek hatalı write tüm projeler için kayıp. Mitigation: atomic temp+rename + provenance.jsonl audit + selffork mind backup global komut.
- **Auto Dream rate-limit storm** — 24h threshold sonrası birden çok proje açıkken çakışma. Mitigation: idempotency_key (`auto_dream_<YYYYMMDD>_<HHMMSS>`), gate-4 active-task check.
- **Pool kavramı kullanıcı sürprizi** — operator hangi pool'a yazdığını her zaman bilmeyebilir. Mitigation: plain-md projection iki ayrı klasörde + provenance UI Logs tab'da pool göstergesi.
- **Identity ayrı tier yok eleştirisi** — operator T7 ister mi? Mitigation: T4+T5 GLOBAL stratum yeterli; ADR-009'da explicit "T7 reddedildi" gerekçesi; gerekirse ADR-010 ile gelecekte eklenir.

### Backward compatibility

- **Mevcut PROJECT verisi** (Order 1-3 PRODUCTION) dokunulmaz. `group_id` field yeni; read-time coalesce.
- **API surface eklenir; mevcut çağrılar bozulmaz**: `MindStore.retrieve(scope=StoreScope(project_slug=...))` çalışmaya devam eder; `PoolScope` opt-in.
- **CLI surface** (`selffork mind`) `--scope=global` / `--scope=hybrid` flag'leri eklenir; default `project` (mevcut davranış).
- **HTTP dashboard `/mind/*`** endpoint'leri `pool` query param eklenir; default `project`.

---

## References

### Internal

- `docs/decisions/ADR-002_Mind_Architecture.md` — 6-tier mimari, storage, eval suite.
- `docs/decisions/ADR-006_v2_Pivot.md` §7 — self-host vision.
- `docs/decisions/ADR-008_Autonomy_Heartbeat.md` §3-§5 — Heartbeat outer loop + audit.jsonl source.
- `packages/mind/src/selffork_mind/store/base.py` — `StoreScope` Pydantic model.
- `packages/mind/src/selffork_mind/store/duckdb.py` — DuckDB MindStore reference impl.
- `packages/orchestrator/src/selffork_orchestrator/heartbeat/audit.py` — T2 Episodic feed source.
- `packages/mind/tests/test_store_duckdb.py` — 53 test PROJECT pool coverage.

### External / Papers (ADR-002 dışı yeni)

- Graphiti `group_id` bi-temporal — Rasmussen et al. 2025, arXiv:2501.13956. `examples_crucial/graphiti/graphiti_core/edges.py:51,263-285`.
- Letta `BlocksAgents` m2m — `examples_crucial/letta/letta/orm/blocks_agents.py:7-34`; `letta/services/agent_manager.py:2162` `attach_block_async`.
- mem0 hash dedup — `examples_crucial/mem0/mem0/memory/main.py:799-803`.
- mem0 sigmoid BM25 + adaptive max_possible — `examples_crucial/mem0/mem0/utils/scoring.py:31-110`.
- Cognee UUID5 + Annotated markers — `examples_crucial/cognee/cognee/infrastructure/engine/models/DataPoint.py:65-162`.
- Anthropic Memory Tool — https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- Anthropic Auto Dream — https://claudefa.st/blog/guide/mechanics/auto-dream (3rd party deep-dive); grandamenium/dream-skill MIT replication.
- Claude Code CLAUDE.md hierarchy — https://code.claude.com/docs/en/memory
- mcp-memory-service — https://github.com/doobidoo/mcp-memory-service (Apache 2.0, autonomous consolidation reference).
- AGENTS.md cross-tool standard — https://agents.md/ (60k+ repos, Linux Foundation).
- Cursor Memories deprecation lesson — https://forum.cursor.com/t/custom-modes-and-memories-gone-in-2-1/143744

### Operator directive

> 2026-05-23 00:11 GMT+3: *"hivemind sadece örnekti başka açık kaynakları da araştırıcaz sonra ve en iyi proje bazlı ve ayrıca ortak genel memory havuzunu yaratıcaz!"*

> 2026-05-23 02:00 GMT+3: *"S-memory öle salla pati olmamalı tam kapsamlı enterprise kalitede olmalı self jr farklı farklı cli leri tek proje yapaarken döndüreceğinden her bir cli nin aynı projede aynı memory havuzuna ve aynı zamanda genel bir de memory havuzuna ihtiyaç duyacaklardır"*

---

## Onay

Operatör 2026-05-23 ~02:11 GMT+3 4 AskUserQuestion'da (Pool primitive / T-pool mapping / T5 trigger / ADR strategy) önerilen seçimlerin hepsini onayladı. ADR-009 **Approved**.
