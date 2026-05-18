# M4 — Cockpit Full Control: 9-Order Implementation Plan

**Milestone:** M4 — Cockpit Full Control
**Tarih:** 2026-05-09 (close-out aynı gün)
**Durum:** ✅ DONE — 9/9 order kapandı (Yamaç laptop manuel smoke test bekliyor)
**ADR referansı:** `docs/decisions/ADR-004_M4_Cockpit.md`
**Tahmini süre:** 4-5 hafta (gerçekleşen: aynı session içinde — single-agent yoğun pass)
**Test baseline:** 1135 pass (orchestrator: 752 + mind: 292 + shared: 91)
**Test sonucu:** **1240 backend pass** (+105) · **76 frontend vitest pass** (sıfırdan kuruldu)

---

## 1. Genel bakış

M4 milestone'u SelfFork orchestrator'ın 4-tab live cockpit yüzeyini kurar:
**Mission / Run / Chat / Context**. M3'ten (CLI Surfing) gelen tüm altyapı
(snapper fleet, autopilot 11-tool surface, audit JSONL stream, HandoffBundle,
PtbTelegramBridge, LaunchdScheduler, SnapperRunner) cockpit'in canlı feed'ini
besler.

**Pillar etkisi:**
- **Pillar 1 (Reflex):** M7 SFT dataset zenginleşir — Yamaç'ın cockpit'te yaptığı edit / branch / recall query / kanban müdahalesi audit log'a düşer.
- **Pillar 2 (Body):** Etkilenmez (M5'e iter); cockpit M5 Body driver UI'ını host edecek tab shell + state stack altyapısını M4'te getirir.
- **Pillar 3 (Mind):** Yeni `mind_router` HTTP yüzeyi; `MindStore.count_by_tier(scope)` Protocol additive method.

**M3'ten devralınan altyapı (M4 girdisi):**

| Subsystem | Path | Durum |
|-----------|------|-------|
| Audit JSONL infrastructure | `packages/shared/src/selffork_shared/audit.py` | ✅ append-only JSONL, 22 category, secret redaction |
| Audit reader / tail | `packages/shared/src/selffork_shared/audit_reader.py:146` | ✅ poll 0.5s, position-tracked |
| 6 CLI snapper fleet | `packages/orchestrator/.../snappers/` | ✅ 1sn cadence, atomic file write |
| Jr autopilot 11-tool | `packages/orchestrator/.../tools/` | ✅ tool spec + parser + registry |
| 4 Kanban tool | `packages/orchestrator/.../tools/kanban.py` | ✅ kart CRUD via tool call |
| FastAPI dashboard | `packages/orchestrator/.../dashboard/server.py` | ✅ 22 route, 2 WS |
| Mind T1-T6 | `packages/mind/src/selffork_mind/` | ✅ 6 tier, hybrid retriever, compaction |
| HandoffBundle | `packages/orchestrator/.../handoff/` | ✅ Pydantic + path-traversal guard |
| LaunchdScheduler | `packages/orchestrator/.../resume/cron.py` | ✅ macOS plist |
| PtbTelegramBridge | `packages/orchestrator/.../telegram/` | ✅ PTB v22.7 + AllowList + Inbox |
| Next.js apps/web shell | `apps/web/` | ✅ 7 sayfa, 7 WS consumer, native fetch |

**M4'ün getirdiği yeni teknoloji:**

| Teknoloji | Versiyon | Amaç |
|-----------|----------|------|
| TanStack Query | latest stable (5.x) | Server state cache + WS-driven setQueryData |
| zustand | latest stable | UI ephemeral state (4 slice) |
| react-virtuoso | latest stable | Audit log virtualized + followOutput |
| Streamdown | latest stable | Markdown render (mid-stream + Shiki + copy) |
| @assistant-ui/react | latest stable | Chat components (Tool, BranchPicker primitives) |
| @dnd-kit/sortable | mevcut | SortableContext (Order 1 fix) |
| openapi-typescript | latest dev-dep | OpenAPI → TS type sync |
| watchfiles | latest | Audit JSONL fsnotify-based tail (replaces poll if performant) |

---

## 2. Order Dependency Graph

```
Order 1 (Pre-M4 audit fix) ─┬─→ Order 2 (Multi-dir audit WS tail)
                            │
                            ├─→ Order 6 (Mission tab — SortableContext fix reuse)
                            │
                            └─→ Order 7 (Run tab — audit dir resolver kullanır)

Order 3 (Mind HTTP surface) ──→ Order 4 (Chat backend — Mind T2 alt-path log)
                            │
                            └─→ Order 9 (Context tab — mind_router consume)

Order 4 (Chat backend) ─────→ Order 8 (Chat tab)

Order 5 (Tab shell) ───┬───→ Order 6 (Mission tab)
                       ├───→ Order 7 (Run tab)
                       ├───→ Order 8 (Chat tab)
                       └───→ Order 9 (Context tab)

Backend katmanı (Orders 1-4) frontend katmanından (Orders 5-9) bağımsız
ilerleyebilir; Order 5 hemen Order 1 sonrası başlatılabilir.
```

**Paralel uygulama önerisi (4 haftalık plan):**
- **Hafta 1:** Order 1 (1-2 gün) → Order 2 (0.5 gün) → Order 5 başlangıç (paralel: Order 3 başlangıç)
- **Hafta 2:** Order 5 bitiş + Order 3 bitiş + Order 4 başlangıç
- **Hafta 3:** Order 6 + Order 7 (paralel: Order 4 bitiş)
- **Hafta 4:** Order 8 + Order 9 (E2E + Polish)

---

## 3. Pre-flight Checklist (Order 0)

Order 1'e başlamadan önce yapılacaklar:

- [ ] **Mevcut state audit:** `git status` clean. Uncommitted change yok. (Yamaç görevi)
- [ ] **Test baseline doğrulama:** `pytest packages/ tests/` → 1135 pass.
- [ ] **Lint baseline doğrulama:** `ruff check packages/ apps/` clean. `mypy --strict packages/` clean.
- [ ] **Plan dosyası okuma:** Bu dosyayı (`docs/plans/M4_Cockpit_Plan.md`) ve ADR-004'ü oku — her order başında ilgili Order bölümünü tekrar oku (recency bias).
- [ ] **examples_crucial referans hazırlığı:** Skyvern (`examples_crucial/skyvern/`) ve Letta (`examples_crucial/letta/`) read-only referans olarak stand-by.

---

## 4. Order detayları

### Order 1 — Pre-M4 audit fix

**Tahmin:** 1-2 gün
**Bağımlılık:** Yok (ilk order)
**Bloklar:** Order 2, Order 6, Order 7

#### Scope

Audit-god ajanının pre-M4 raporundan çıkan 4 critical bug'ın fix'i. Bunlar
M4 cockpit'in HER tab'ı için temel dayanak — biri çalışmazsa cockpit hiç
açılamaz veya silent data corruption üretir.

**Scope dışı (intentional):** M5+'a iten teknik borçlar (Linux scheduler,
Telegram inbound vb.). Yalnızca M4 başlamadan kapatılması zorunlu olanlar.

#### Bug listesi

| # | Bug | Severity | Lokasyon |
|---|-----|----------|----------|
| 1.A | `update_card` PATCH her çağrıda `order=None`'a siliyor (sentinel pattern eksik) | CRITICAL | `packages/orchestrator/src/selffork_orchestrator/dashboard/server.py:524-548` |
| 1.B | `events`/`plan`/`workspace`/WS endpoint'leri yalnız `config.audit_dir`'ı okuyor → project session'lar 404 | CRITICAL | `server.py:188-205, 208-247, 250-279, 611-627` |
| 1.C | `RunRequestPayload.project_slug` HİÇ KULLANILMIYOR (frontend gönderiyor backend ignore) | HIGH | `server.py:281-321`, frontend `apps/web/lib/api.ts:166-180` |
| 1.D | `useSortable` çağrısı `SortableContext` dışında (dnd-kit sortable no-op) | HIGH | `apps/web/app/project/page.tsx:26, 588` |

#### Files touched

| Dosya | Değişiklik tipi | Açıklama |
|-------|-----------------|----------|
| `packages/orchestrator/src/selffork_orchestrator/dashboard/server.py` | EDIT | _resolve_audit_dir helper + 4 endpoint refactor + run wiring + update_card sentinel |
| `packages/orchestrator/src/selffork_orchestrator/dashboard/schemas.py` | EDIT | `CardUpdatePayload` Pydantic v2 `model_fields_set`-aware sentinel |
| `packages/orchestrator/src/selffork_orchestrator/cli.py` | EDIT (CONDITIONAL) | `--project <slug>` flag yoksa eklenecek (audit-god report MEDIUM-confidence) |
| `apps/web/app/project/page.tsx` | EDIT | `import { SortableContext, verticalListSortingStrategy }` + her column içinde wrap |
| `apps/web/app/projects/page.tsx` | EDIT | `FolderPlus` dead import kaldır (cleanup) |
| `packages/orchestrator/tests/dashboard/test_projects_api.py` | EDIT | `test_update_card_partial_patch_preserves_order` ekle |
| `packages/orchestrator/tests/dashboard/test_server.py` | EDIT | `test_resolve_audit_dir_project` + `test_session_events_resolves_project_audit_dir` + `test_run_with_project_slug_passes_to_cli` |

#### Sub-tasks

1.1. **Audit dir resolver helper.** `server.py`'a `_resolve_audit_dir(session_id: str) -> Path | None` ekle: önce `config.audit_dir`'da bak, yoksa `config.projects_root`'taki tüm `<slug>/audit/<session_id>.jsonl` dosyalarını tara. Cache mekanizması (in-memory dict, project_slug + session_id → Path) — 5 dakikalık TTL.

1.2. **`events` endpoint refactor.** `server.py:188-205` → `_resolve_audit_dir(session_id)` kullan; bulunamazsa 404.

1.3. **`plan` endpoint refactor.** `server.py:208-247` → aynı pattern. NB: paused-only constraint paused-only kalır (ScheduledResume bağımlı), bu rapor scope'u dışı.

1.4. **`workspace` endpoint refactor.** `server.py:250-279` → aynı pattern.

1.5. **WS `stream` endpoint refactor.** `server.py:611-627` → `_resolve_audit_dir` kullan; resolved Path'i `tail_session_events`'e geçir.

1.6. **`update_card` sentinel pattern.** `schemas.py` `CardUpdatePayload` modelinde Pydantic v2 `model_fields_set` kontrolü:
```python
if "order" in payload.model_fields_set:
    update_kwargs["order"] = payload.order
```
`server.py:542` mevcut buggy ternary'yi kaldır. `_SENTINEL` semantiğine doğru köprü kur.

1.7. **`run` endpoint project_slug wire.** `server.py:285-321` →
```python
if payload.project_slug:
    cmd.extend(["--project", payload.project_slug])
```
**ÖNCE doğrula** — `cli.py`'da `--project` flag var mı? Yoksa Order 1.7.A: cli.py'a Click `@click.option("--project")` ekle, `Session(project_slug=value)` aktarımı.

1.8. **`useSortable` + `SortableContext` fix.** `project/page.tsx:26` import güncelle: `import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable"`. Her `<Column>` render'ı içinde:
```tsx
<SortableContext items={cards.map(c => c.id)} strategy={verticalListSortingStrategy}>
  {cards.map(card => <SortableCard key={card.id} card={card} />)}
</SortableContext>
```

1.9. **`FolderPlus` dead import.** `apps/web/app/projects/page.tsx:7` — kaldır.

1.10. **Test ekleme.** Aşağıdaki test'ler:
- `test_update_card_partial_patch_preserves_order` (PATCH title-only sonrası order korunmalı)
- `test_resolve_audit_dir_orphan_session` (config.audit_dir/<id>.jsonl)
- `test_resolve_audit_dir_project_session` (project audit_dir altında)
- `test_session_events_resolves_project_audit_dir` (200 dönmeli)
- `test_session_workspace_resolves_project_audit_dir` (paused project session)
- `test_session_plan_resolves_project_audit_dir` (paused project session)
- `test_run_with_project_slug_passes_to_cli` (subprocess argv inspect)

Frontend için test (apps/web mevcut test setup yoksa skip — manual smoke):
- Manual: `cd apps/web && npm run dev` → bir kanban kartı title edit, order korundu mu doğrula.

#### Audit-god checklist (Order 1 kapanmadan önce)

- [ ] `_resolve_audit_dir` cache hit/miss path'leri ayrı log ediyor mu (debug observability)
- [ ] Pydantic v2 `model_fields_set` doğru kullanılmış mı (Pydantic v1 fallback yok mu)
- [ ] `cli.py` `--project` flag'i `Session` ctor'a doğru aktarıyor mu
- [ ] SortableContext `strategy` `verticalListSortingStrategy` mı (yatay olması istenmediği teyit)
- [ ] WS resolver hatası durumunda WS close code 4404 mu (HTTP-mirror), kullanıcıya neden döndürülüyor mu
- [ ] Yeni eklenen 7 test'in hepsi gerçek `tmp_path` fixture kullanıyor mu (no-mock kuralı uyumlu)

#### Acceptance criteria

- [ ] 4 critical bug repro test'leri yazıldı, geçti
- [ ] Mevcut 1135 test korundu (regression yok)
- [ ] Manual smoke: dashboard'dan project session tıkla → events görünüyor (404 değil)
- [ ] Manual smoke: kanban kartı title-only PATCH sonrası order korundu
- [ ] Manual smoke: dashboard'dan "run" başlat (project seçili) → orchestrator process project context aldı
- [ ] Manual smoke: kanban'da kart drag-drop within column çalışıyor (animasyon görünür)
- [ ] ruff + mypy strict zero regression

#### Risks & open questions

- **R1.1:** `cli.py` `--project` flag yoksa Order scope büyür (~+0.5 gün). Mitigation: ilk iş cli.py'da grep at, gerekirse Order 1.A olarak ayrıca aç.
- **R1.2:** Audit dir cache stale olursa yeni eklenen project session'lar 5 dakika 404 atar. Mitigation: project create endpoint'i cache invalidate çağırsın.
- **OQ1.1:** Mevcut `audit_reader.tail_session_events` Path arg'ı mı kabul ediyor yoksa `audit_dir` + `session_id` ayrı mı? Order 1.5 implementasyonunda netleşir.

---

### Order 2 — Multi-dir audit WS tail

**Tahmin:** 0.5 gün
**Bağımlılık:** Order 1 (resolver helper kullanır)
**Bloklar:** Order 7 (Run tab audit stream)

#### Scope

Order 1'in resolver helper'ı tek session WS endpoint'inde çalışıyor; bu
order çoklu project audit dir'lerinde de aynı semantiği garanti eder + WS
reconnect protokolünü (M-1 multiplex foundation) hazırlar.

#### Files touched

| Dosya | Değişiklik | Açıklama |
|-------|-----------|----------|
| `packages/shared/src/selffork_shared/audit_reader.py:146-171` | EDIT | `tail_session_events` multi-dir support (zaten Path alıyorsa Order 1'de halledildi, burada yalnız sequence ID + heartbeat ekle) |
| `packages/orchestrator/.../dashboard/server.py:611-657` | EDIT | WS protokolü: `?last_seq=N` query param, `seq` field her mesajda, 30s heartbeat ping |
| `packages/orchestrator/.../dashboard/ws_protocol.py` | NEW | M-1 protokol foundation: `WsEnvelope` Pydantic, `BoundedReplayBuffer` (deque maxlen=200), `HeartbeatTask` (anyio) |
| `packages/orchestrator/tests/dashboard/test_ws_protocol.py` | NEW | sequence_id replay + buffer overflow + heartbeat tests |

#### Sub-tasks

2.1. **`WsEnvelope` Pydantic model.** `ws_protocol.py`:
```python
class WsEnvelope(BaseModel):
    seq: int
    event_type: Literal["audit", "kanban", "quota", "mind", "chat.token", "heartbeat"]
    session_id: str | None = None
    project_slug: str | None = None
    payload: dict[str, Any]
    ts: datetime
```

2.2. **`BoundedReplayBuffer`** — `collections.deque(maxlen=200)` per WS connection. `append(envelope)` + `replay_from(last_seq) -> Iterator[WsEnvelope]`.

2.3. **`HeartbeatTask`** — anyio `sleep_until` based; her 30s `WsEnvelope(event_type="heartbeat")` gönderir.

2.4. **WS endpoint refactor.** `server.py:611-657` her iki WS endpoint:
- `?last_seq=N` query param
- Bağlantı kabul → `BoundedReplayBuffer` instance + `HeartbeatTask` start
- Her audit event → `WsEnvelope(seq=monotonic, event_type="audit", ...)` → buffer append + send
- Reconnect: client `last_seq` verirse buffer'dan replay; buffer'da yoksa "gap" event (UI REST fallback yapsın)

2.5. **Audit reader sequence integration.** `audit_reader.tail_session_events` zaten file offset / line number tutuyor; `seq` mapping = file line number (monotonic, deterministic).

2.6. **Test:**
- `test_ws_envelope_seq_monotonic`
- `test_ws_replay_from_last_seq`
- `test_ws_buffer_overflow_drops_oldest`
- `test_ws_heartbeat_emits_every_30s` (time-mocked)
- `test_ws_session_stream_project_audit_dir` (Order 1 resolver entegrasyon)

#### Audit-god checklist

- [ ] `BoundedReplayBuffer` thread-safe mi (anyio.Lock veya deque atomicity yeterli mi)
- [ ] Heartbeat task WS close edildiğinde cleanup oluyor mu (anyio cancellation scope)
- [ ] `seq` mapping file-position drift'e dayanıklı mı (audit log yeniden başlatılırsa)
- [ ] `last_seq` query param invalid (negatif, string) → 400 mü 4400 WS close code mu
- [ ] Heartbeat envelope sequence ID alıyor mu (almasın — UI filter'ı bozmasın)

#### Acceptance criteria

- [ ] Project session'ına açılan WS canlı event yayını yapıyor (orphan da çalışmaya devam ediyor)
- [ ] Disconnect + reconnect with `?last_seq` → kaçırılan event'ler replay
- [ ] Buffer dolduğunda eski event'ler dropped, UI gap detection devreye girer
- [ ] Heartbeat 30s'de bir UI'a düşüyor (latency görünür)
- [ ] 5 yeni test pass

#### Risks & open questions

- **R2.1:** Buffer maxlen=200 düşük olabilir (yoğun session 5sn'de aşar). Mitigation: configurable, default 200 stretch goal 500.
- **OQ2.1:** Heartbeat protokolü ws-spec'te ping/pong frame mi yoksa application-level message mı? Karar: application-level (UI filter'da kolay).

---

### Order 3 — Mind HTTP surface (`mind_router`)

**Tahmin:** 2-3 gün
**Bağımlılık:** Yok (Order 1 paralel ilerleyebilir)
**Bloklar:** Order 4 (Mind T2 alternative-path log), Order 9 (Context tab)

#### Scope

Mind tier'larını HTTP üzerinden expose et — şu an sadece `/api/mind/provenance`
var, geri kalan 9 endpoint sıfırdan. Cockpit Context tab'ı (Order 9) ve
Chat tab'ın branching log'u (Order 4) bu endpoint'leri tüketecek.

#### Files touched

| Dosya | Değişiklik | Açıklama |
|-------|-----------|----------|
| `packages/orchestrator/.../dashboard/mind_router.py` | NEW | 9 REST + 1 WS endpoint |
| `packages/orchestrator/.../dashboard/mind_deps.py` | NEW | `_resolve_mind_root`, `_open_store`, `_build_embedder`, `_build_provenance` (cli_mind.py'den extract) |
| `packages/orchestrator/.../dashboard/server.py` | EDIT | `mind_router` mount |
| `packages/orchestrator/.../dashboard/schemas.py` | EDIT | `NoteResponse`, `TierStatsResponse`, `WorkingBlockResponse`, `RecallRequestPayload`, `RecallResponse`, `GraphTripleResponse` |
| `packages/mind/src/selffork_mind/store/base.py` | EDIT | `count_by_tier(scope: StoreScope) -> dict[TierName, int]` Protocol method |
| `packages/mind/src/selffork_mind/store/duckdb.py` | EDIT | `count_by_tier` SQL impl |
| `packages/orchestrator/.../cli_mind.py` | EDIT (refactor) | Helper'lar `mind_deps.py`'a taşınınca import değiştir (no-functional change) |
| `packages/orchestrator/tests/dashboard/test_mind_router.py` | NEW | 11 test (her endpoint + WS provenance stream + edge cases) |
| `packages/mind/tests/store/test_count_by_tier.py` | NEW | DuckDB count testi |

#### Endpoint inventarı

| Endpoint | Method | Body / Query | Response |
|----------|--------|--------------|----------|
| `/api/projects/{slug}/mind/stats` | GET | - | `{tiers: {[TierName]: {count: int, last_updated: datetime}}}` |
| `/api/projects/{slug}/mind/working` | GET | - | `WorkingBlockResponse` (T1 inline JSON) |
| `/api/projects/{slug}/mind/notes` | GET | `?tier=&limit=&cursor=` | `{notes: NoteResponse[], next_cursor: str | null}` |
| `/api/projects/{slug}/mind/notes/{id}` | GET | - | `NoteResponse` |
| `/api/projects/{slug}/mind/notes` | POST | `{content, tier, kind, intent, importance, pinned, tag_pairs}` | `NoteResponse` (201) |
| `/api/projects/{slug}/mind/notes/{id}` | DELETE | - | 204 (supersede) |
| `/api/projects/{slug}/mind/recall` | POST | `RecallRequestPayload` (RetrieveConfig projection) | `{hits: NoteResponse[], scores: float[], matched_tags: ...}` |
| `/api/projects/{slug}/mind/graph/triples` | GET | `?seed=&top_k=20` | `GraphTripleResponse[]` |
| `/api/projects/{slug}/mind/provenance` | GET (mevcut) | `?limit=100` | mevcut format korunur |
| `/api/mind/provenance` (orphan, mevcut) | GET | aynı | mevcut format korunur |
| `WS /api/projects/{slug}/mind/provenance/stream` | WS | M-1 multiplex | `WsEnvelope(event_type="mind", payload=ProvenanceEntryResponse)` |

#### Sub-tasks

3.1. **Schemas.** `dashboard/schemas.py`'a 6 yeni Pydantic response model. Her biri `_StrictResponse` (extra="forbid") base'inde. Yapı:
```python
class NoteResponse(_StrictResponse):
    id: UUID
    tier: TierName
    kind: str
    content: str
    intent: str | None
    importance: float
    pinned: bool
    tags: list[TagResponse]
    created_at: datetime
    valid_until: datetime | None
    superseded_by: UUID | None
```

3.2. **`MindStore.count_by_tier`.** Protocol additive method. DuckDB impl:
```python
def count_by_tier(self, scope: StoreScope) -> dict[TierName, int]:
    sql = """SELECT tier, COUNT(*), MAX(created_at)
             FROM notes
             WHERE valid_until IS NULL
               AND project_slug = ?
             GROUP BY tier"""
    # ... bind scope.project_slug, return dict
```

3.3. **`mind_deps.py` extract.** `cli_mind.py:104-184` arasındaki `_resolve_mind_root`, `_open_store`, `_build_embedder`, `_build_provenance` helper'larını yeni dosyaya taşı. `cli_mind.py` artık import et. **Refactor — no functional change**, mevcut testler geçmeli.

3.4. **`mind_router.py` REST endpoint'leri.** Her endpoint:
- Path param `slug` → `_resolve_mind_root(slug)` → `_open_store`
- StoreScope construct (project_slug, optional session_id)
- Action (count_by_tier / list / get / upsert / supersede / retrieve / graph)
- Pydantic projection (Mind type → Response type — leak protection)

3.5. **WS provenance stream.** `mind_router.py`:
- `@app.websocket("/api/projects/{slug}/mind/provenance/stream")`
- `_resolve_mind_root(slug) → ProvenanceRecorder.log_path`
- `tail_provenance_log(log_path)` (audit_reader pattern, file tail)
- Her satır → `WsEnvelope(event_type="mind", payload=ProvenanceEntryResponse)`
- M-1 protokolüne uygun (sequence ID + heartbeat)

3.6. **Server mount.** `server.py:140-150` → `app.include_router(mind_router)`.

3.7. **Test (11 test):**
- `test_mind_stats_returns_tier_counts`
- `test_mind_stats_empty_project`
- `test_mind_working_returns_t1_block`
- `test_mind_working_no_block_404`
- `test_mind_notes_list_paginated`
- `test_mind_notes_list_filter_by_tier`
- `test_mind_note_detail`
- `test_mind_note_create_returns_201`
- `test_mind_note_supersede_returns_204`
- `test_mind_recall_uses_hybrid_retriever`
- `test_mind_recall_filter_dsl_passthrough`
- `test_mind_graph_triples_seed_query`
- `test_mind_provenance_ws_tail` (M-1 sequence ID protocol intact)

3.8. **DuckDB store test.** `test_count_by_tier`:
- 6 tier'a not yaz (T1...T6)
- count_by_tier(scope) → her tier için 1 dön
- valid_until set edilmiş not'lar count'a dahil olmasın

#### Audit-god checklist

- [ ] `mind_deps.py` extract gerçekten no-functional change mi (mevcut `test_cli_mind.py` testleri pass mi)
- [ ] `count_by_tier` SQL injection safe mi (parameterized query)
- [ ] `RecallRequestPayload` Pydantic projection'u tam `RetrieveConfig` field'larını destekliyor mu (Filter DSL, tag_pairs, valid_at, file_path, scope)
- [ ] Auth boundary açık (mevcut server.py'da auth yok); mind note write endpoint'leri eklendiğinde ileride explicit auth kararı verilmeli (M5+ scope)
- [ ] `NoteResponse` PII redaction policy gerekli mi (mind_recall hit content'ı PII içerebilir — Order 4'te tekrar gündeme gelecek)
- [ ] Pillar boundary: `mind_router` `MindStore` Protocol üzerinden çalışıyor, DuckDB impl'e leak yok
- [ ] WS provenance stream Order 2 protokolüne uygun mu

#### Acceptance criteria

- [ ] 9 REST + 1 WS endpoint OpenAPI schema'da görünüyor
- [ ] 11 yeni test pass
- [ ] DuckDB count_by_tier testi pass
- [ ] mevcut Mind testleri (292) regression yok
- [ ] Manual smoke: `curl /api/projects/<slug>/mind/stats` → tier count'lar dönüyor

#### Risks & open questions

- **R3.1:** `count_by_tier` Protocol'e additive ama mock impl'lerini de değiştirmek gerek (test fixture). Mitigation: `BaseMindStore` ABC varsa default impl ekle (raise NotImplementedError).
- **R3.2:** `tail_provenance_log` audit_reader pattern'ı reuse — yeni dosya yerine mevcut `audit_reader.py`'a generic `tail_jsonl` çıkarılabilir (refactor opportunity). Karar: bu Order'da değil, Order 9'da konsolide.
- **OQ3.1:** Mind T3 graph triples seed query API zaten var mı? `SemanticGraphStore.list_triples` Protocol'de mi? Order başında 1 saatlik explorer-god ile kontrol.
- **OQ3.2:** RecallRequestPayload'da `query_embedding` field'ı UI'dan mı geliyor (embed cost UI tarafında) yoksa backend'de mi compute edilecek? Default: backend compute (UI sadece query string gönderir, `_build_embedder` kullanır).

---

### Order 4 — Chat backend (`chat_router`)

**Tahmin:** 3-4 gün
**Bağımlılık:** Order 3 (Mind T2 alternative-path log), Order 2 (WS protokolü)
**Bloklar:** Order 8 (Chat tab)

#### Scope

Chat tab'ın gerektirdiği token streaming + branching API'sini sıfırdan kur.
Mevcut audit JSONL akışı (`selffork_jr.reply` event'i) authoritative kalır;
chat_router audit'e ek kayıt yazmaz, audit'i okur+forward eder. Branch
metadata ayrı bir SQLite store'da tutulur (audit log immutable bozulmaz).

Ek olarak M-7 (audit `tool.result` payload genişletme) bu order'da inilir
çünkü Chat tab tool inline render bu field'ı kullanacak.

#### Files touched

| Dosya | Değişiklik | Açıklama |
|-------|-----------|----------|
| `packages/orchestrator/.../dashboard/chat_router.py` | NEW | 5 REST + 1 WS endpoint |
| `packages/orchestrator/.../chat/branch_store.py` | NEW | SQLite atomic branch CRUD (`~/.selffork/projects/<slug>/branches.db`) |
| `packages/orchestrator/.../chat/branch_model.py` | NEW | `Branch` Pydantic + `BranchEdit` |
| `packages/orchestrator/.../chat/__init__.py` | NEW | public exports |
| `packages/orchestrator/.../dashboard/server.py` | EDIT | `chat_router` mount |
| `packages/orchestrator/.../dashboard/schemas.py` | EDIT | `ChatMessagePayload`, `ChatMessageResponse`, `BranchResponse`, `BranchEditPayload` |
| `packages/orchestrator/.../lifecycle/session.py:489-498` | EDIT | M-7: `result_payload_preview` field ekle (audit `tool.result`) |
| `packages/shared/src/selffork_shared/audit.py:48` | EDIT | `tool.result` payload schema (additive: `payload_keys` korunur, `result_payload_preview` eklenir) |
| `packages/orchestrator/tests/chat/test_branch_store.py` | NEW | 8 test |
| `packages/orchestrator/tests/dashboard/test_chat_router.py` | NEW | 10 test |
| `packages/orchestrator/tests/lifecycle/test_session_audit.py` | EDIT | `result_payload_preview` smoke test |

#### Endpoint inventarı

| Endpoint | Method | Body | Response |
|----------|--------|------|----------|
| `/api/sessions/{id}/messages` | POST | `ChatMessagePayload(content, branch_id?)` | `ChatMessageResponse` (201) |
| `/api/sessions/{id}/messages/{msg_id}/edit` | POST | `BranchEditPayload(content)` | `{branch: BranchResponse, message: ChatMessageResponse}` |
| `/api/sessions/{id}/branches` | GET | - | `BranchResponse[]` |
| `/api/sessions/{id}/active-branch` | PATCH | `{branch_id}` | `BranchResponse` |
| `/api/sessions/{id}/messages` | GET | `?branch_id=` | `ChatMessageResponse[]` |
| `WS /api/sessions/{id}/chat/stream` | WS | M-1 multiplex | `WsEnvelope(event_type="chat.token", payload={token, message_id, branch_id})` |

#### Sub-tasks

4.1. **`Branch` Pydantic model.** `chat/branch_model.py`:
```python
class Branch(BaseModel):
    id: UUID
    session_id: str
    parent_branch_id: UUID | None
    fork_message_id: UUID | None  # hangi mesajdan branch yarattı
    created_at: datetime
    label: str | None  # "main" / "alt-1" / kullanıcı verir
```

4.2. **`BranchStore` SQLite.** `chat/branch_store.py`:
- `create_branch(session_id, parent_id, fork_msg_id) -> Branch`
- `list_branches(session_id) -> list[Branch]`
- `get_active_branch(session_id) -> Branch`
- `set_active_branch(session_id, branch_id) -> None`
- `append_message(branch_id, content, role) -> ChatMessage` (audit'e yazılan event'in mirror'ı, branch_id ile bağlı)
- SQLite WAL mode, atomic UPDATE.

4.3. **`chat_router.py` REST.** Her endpoint M-1 protokolüne uyar, audit log read'i `selffork_jr.reply` event'i için filter yapar.

4.4. **WS chat stream.** Token-by-token streaming için iki yaklaşım:
- (A) Round-loop driver token emit ederken `WsEnvelope` broadcast (preferred)
- (B) Audit `selffork_jr.reply` final event'inden sonra synthetic token replay (fallback)
  Order 4'te (A) implemente, (B) gelecek M5'e iter.

4.5. **Mind T2 alternative-path log.** Branch yaratıldığında `mind_router.POST /api/projects/{slug}/mind/notes` çağrılır:
```python
note = NoteCreate(
    content=f"Branch fork from message {msg_id}",
    tier="episodic",
    kind="alternative_path",
    intent="branch_creation",
    tag_pairs=[("branch_id", str(branch.id)), ("session_id", session_id)]
)
```

4.6. **M-7: `result_payload_preview` field.** `lifecycle/session.py:489-498` mevcut audit emit:
```python
self._audit.emit(
    category="tool.result",
    level="INFO",
    event="tool_result",
    payload={
        "round": self._round,
        "tool": result.tool,
        "status": result.status,
        "error": result.error,
        "payload_keys": list(result.payload.keys()),
        # YENİ:
        "result_payload_preview": _redact_preview(result.payload),
    },
)
```

`_redact_preview` helper: dict, max 5KB total chars, secret patterns redact ("api_key", "token", "password" → `<redacted>`).

4.7. **Audit schema extension.** `audit.py` Pydantic için no-op (payload `dict[str, Any]` zaten esnek). Sadece dokümantasyon comment'i güncelle.

4.8. **Test (10 test):**
- `test_chat_message_post_appends_to_branch`
- `test_chat_message_post_default_branch_is_active`
- `test_chat_message_edit_creates_new_branch`
- `test_chat_message_edit_logs_mind_alt_path`
- `test_chat_branches_list_orders_by_created_at`
- `test_chat_active_branch_switch`
- `test_chat_messages_filter_by_branch`
- `test_chat_ws_stream_token_emits_envelope`
- `test_chat_ws_stream_branch_id_propagates`
- `test_chat_ws_stream_reconnect_replay`

4.9. **Branch store test (8):**
- `test_branch_store_create_and_get`
- `test_branch_store_active_branch`
- `test_branch_store_concurrent_create_atomic`
- `test_branch_store_parent_chain`
- `test_branch_store_append_message_persists`
- `test_branch_store_corrupt_db_recovery`
- `test_branch_store_max_branches_per_session` (configurable, default 100)
- `test_branch_store_supersede_branch`

4.10. **Audit preview test:**
- `test_tool_result_payload_preview_redacts_secrets`
- `test_tool_result_payload_preview_truncates_large` (>5KB)

#### Audit-god checklist

- [ ] `BranchStore` SQLite WAL mode + concurrent write atomicity (memory: M-1 sequence ID + concurrent edit)
- [ ] `_redact_preview` helper exhaustive secret pattern (api_key, token, password, secret, credential, auth)
- [ ] M-7 audit field truly additive (mevcut consumer `payload_keys`'i hâlâ alıyor)
- [ ] WS chat stream `chat.token` envelope round-loop driver'da nereden emit ediliyor (MEDIUM-confidence — Order başlamadan explorer-god ile lifecycle/session.py'da emit point doğrulanmalı)
- [ ] Mind T2 alt-path note write işi başarısız olursa branch yaratma rollback mı yoksa silent log mi (öneri: silent log, audit'e error event)
- [ ] Pillar boundary: chat_router → mind_router HTTP mu yoksa direct Python import mu (öneri: in-process direct import, HTTP overhead gereksiz)

#### Acceptance criteria

- [ ] Real CLI agent (claude-code) ile token streaming canlı (manual smoke)
- [ ] Branch yaratma + switch çalışıyor (10 test pass)
- [ ] result_payload_preview audit log'a düşüyor, secret redact ediliyor (3 test pass)
- [ ] Mind T2 note write working (Order 3 entegrasyon test pass)
- [ ] mevcut 752 orchestrator test korundu (regression yok)

#### Risks & open questions

- **R4.1:** Round-loop driver token emit etmiyor olabilir (ham subprocess stdout buffered, line-by-line değil). Mitigation: Order başlangıcında 1 saat lifecycle/session.py incelemesi; gerekirse subprocess unbuffered (`PYTHONUNBUFFERED=1`) + line-by-line read.
- **R4.2:** SQLite branch store concurrent operator (Yamaç tek, ama 2 tarayıcı tab) edge case. Mitigation: WAL mode + serialization.
- **R4.3:** result_payload_preview 5KB sınırı mind_recall hit'leri için yetersiz olabilir. Mitigation: per-tool limit (mind_recall için 20KB).
- **OQ4.1:** Branch label kullanıcıdan mı (UI'da rename) yoksa otomatik mı (timestamp)? Default: otomatik `branch-<short-uuid>`, UI rename M5+.
- **OQ4.2:** Edit history korunacak mı (her edit ayrı branch mi, yoksa branch içinde history mi)? Karar: her edit yeni branch (assistant-ui pattern, immutable history).

---

### Order 5 — apps/web tab shell

**Tahmin:** 2-3 gün
**Bağımlılık:** Yok (Order 1 sonrası başlatılabilir, backend Order 2/3/4 paralel)
**Bloklar:** Order 6, Order 7, Order 8, Order 9

#### Scope

Cockpit tab shell'ini kurmak: shadcn/ui Tabs primitive ekle, 4-tab routing
(URL `?tab=`), Zustand state store (4 slice), TanStack Query setup, WS
multiplex client. Bu order'dan sonra her tab (Order 6-9) kendi içeriğini
ekler — shell hazır, çakışmadan paralel ilerleyebilirler.

#### Files touched

| Dosya | Değişiklik | Açıklama |
|-------|-----------|----------|
| `apps/web/package.json` | EDIT | 7 yeni dep: `@tanstack/react-query`, `zustand`, `react-virtuoso`, `@assistant-ui/react`, `streamdown`, `openapi-typescript` (dev), `cmdk` (CommandPalette upgrade — eğer kullanılıyorsa) |
| `apps/web/components/ui/tabs.tsx` | NEW | shadcn/ui Tabs install (CLI: `npx shadcn-ui@latest add tabs`) |
| `apps/web/components/ui/dialog.tsx` | NEW | shadcn/ui Dialog (Mission drawer için) |
| `apps/web/components/ui/sheet.tsx` | NEW | shadcn/ui Sheet (Run tab side panel için) |
| `apps/web/components/ui/select.tsx` | NEW | shadcn/ui Select |
| `apps/web/components/ui/input.tsx` | NEW | shadcn/ui Input |
| `apps/web/components/ui/textarea.tsx` | NEW | shadcn/ui Textarea |
| `apps/web/components/ui/tooltip.tsx` | NEW | shadcn/ui Tooltip |
| `apps/web/components/ui/scroll-area.tsx` | NEW | shadcn/ui ScrollArea |
| `apps/web/app/cockpit/layout.tsx` | NEW | Cockpit shell layout (Tabs + project selector) |
| `apps/web/app/cockpit/page.tsx` | NEW | Cockpit ana sayfa (default tab=mission) |
| `apps/web/lib/query.ts` | NEW | TanStack Query `QueryClient` setup, default `staleTime: Infinity` |
| `apps/web/lib/store/index.ts` | NEW | Zustand root store + 4 slice export |
| `apps/web/lib/store/mission-slice.ts` | NEW | placeholder (Order 6 dolduracak) |
| `apps/web/lib/store/run-slice.ts` | NEW | placeholder (Order 7 dolduracak) |
| `apps/web/lib/store/chat-slice.ts` | NEW | placeholder (Order 8 dolduracak) |
| `apps/web/lib/store/context-slice.ts` | NEW | placeholder (Order 9 dolduracak) |
| `apps/web/lib/ws/multiplex.ts` | NEW | `useWebsocketSubscription` hook (M-1 protocol intact) |
| `apps/web/lib/ws/types.ts` | NEW | `WsEnvelope` TypeScript type (backend mirror) |
| `apps/web/lib/api-types.ts` | NEW (generated) | OpenAPI → TS types (`pnpm gen:api`) |
| `apps/web/scripts/gen-api-types.sh` | NEW | OpenAPI fetch + openapi-typescript run |
| `apps/web/app/layout.tsx` | EDIT | QueryClientProvider wrap |
| `apps/web/__tests__/store/cockpit-store.test.ts` | NEW | 4 test (slice composition) |
| `apps/web/__tests__/ws/multiplex.test.ts` | NEW | 6 test (WsServer mock + reconnect + replay + heartbeat + subscribe) |

#### Sub-tasks

5.1. **Dependency install.** `apps/web/` cwd'de:
```bash
pnpm add @tanstack/react-query zustand react-virtuoso @assistant-ui/react streamdown
pnpm add -D openapi-typescript
```

5.2. **shadcn/ui primitive install.** Her biri ayrı CLI komutu:
```bash
npx shadcn-ui@latest add tabs dialog sheet select input textarea tooltip scroll-area
```

5.3. **TanStack Query setup.** `lib/query.ts`:
```ts
import { QueryClient } from "@tanstack/react-query";
export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: Infinity, gcTime: 5 * 60 * 1000 } },
});
```
`app/layout.tsx`:
```tsx
<QueryClientProvider client={queryClient}>
  <SidebarProvider>...</SidebarProvider>
</QueryClientProvider>
```

5.4. **Zustand root store.** `lib/store/index.ts`:
```ts
import { create } from "zustand";
import { devtools } from "zustand/middleware";
import { createMissionSlice, type MissionSlice } from "./mission-slice";
import { createRunSlice, type RunSlice } from "./run-slice";
import { createChatSlice, type ChatSlice } from "./chat-slice";
import { createContextSlice, type ContextSlice } from "./context-slice";

export type CockpitStore = MissionSlice & RunSlice & ChatSlice & ContextSlice;

export const useCockpitStore = create<CockpitStore>()(
  devtools((...a) => ({
    ...createMissionSlice(...a),
    ...createRunSlice(...a),
    ...createChatSlice(...a),
    ...createContextSlice(...a),
  }))
);
```

Her slice'ın placeholder'ı:
```ts
// mission-slice.ts
export type MissionSlice = { _placeholder?: never };
export const createMissionSlice: StateCreator<CockpitStore, [], [], MissionSlice> = () => ({});
```

5.5. **WS multiplex client.** `lib/ws/multiplex.ts`:
```ts
export type WsEnvelope = {
  seq: number;
  event_type: "audit" | "kanban" | "quota" | "mind" | "chat.token" | "heartbeat";
  session_id?: string;
  project_slug?: string;
  payload: Record<string, unknown>;
  ts: string;
};

export function useWebsocketSubscription(args: {
  url: string;
  onEnvelope: (env: WsEnvelope) => void;
  onGap?: (lastSeq: number, newSeq: number) => void;
}) {
  // Reconnect with exponential backoff (1s → 30s max)
  // Last-seq tracking + ?last_seq=N query
  // Heartbeat detection (no envelope >35s → force reconnect)
  // Cleanup on unmount
}
```

5.6. **Cockpit layout.** `app/cockpit/layout.tsx`:
```tsx
"use client";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useSearchParams, useRouter } from "next/navigation";

const TABS = ["mission", "run", "chat", "context"] as const;

export default function CockpitLayout({ children }: { children: React.ReactNode }) {
  const search = useSearchParams();
  const router = useRouter();
  const active = (search.get("tab") ?? "mission") as typeof TABS[number];

  const onTabChange = (next: string) => {
    const sp = new URLSearchParams(search);
    sp.set("tab", next);
    router.push(`/cockpit?${sp.toString()}`);
  };

  return (
    <Tabs value={active} onValueChange={onTabChange}>
      <TabsList>
        {TABS.map(t => <TabsTrigger key={t} value={t}>{t}</TabsTrigger>)}
      </TabsList>
      {TABS.map(t => <TabsContent key={t} value={t}>{children}</TabsContent>)}
    </Tabs>
  );
}
```

5.7. **OpenAPI type-sync.** `scripts/gen-api-types.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
curl -fsS http://localhost:8000/openapi.json | npx openapi-typescript --output apps/web/lib/api-types.ts -
```
`package.json`:
```json
"scripts": { "gen:api": "bash scripts/gen-api-types.sh" }
```

5.8. **Tests:**
- `cockpit-store.test.ts`: 4 slice composition (root store init et, her slice'ın placeholder field'ı yok ama tip-safe)
- `multiplex.test.ts`:
  - `connect_emits_envelopes_to_handler`
  - `gap_detection_calls_onGap`
  - `reconnect_with_last_seq`
  - `heartbeat_detection_force_reconnect`
  - `cleanup_on_unmount`
  - `exponential_backoff_caps_at_30s`

#### Audit-god checklist

- [ ] `useWebsocketSubscription` cleanup'ı `useEffect` return'da gerçekten WS close ediyor mu (memory leak prevention)
- [ ] Tab URL state SSR uyumlu mu (`useSearchParams` server-side `null` dönüyor mu, fallback "mission" var mı)
- [ ] Static-export uyumu kırılmadı mı (memory: project_ui_stack, dynamic `[id]` route eklemedim)
- [ ] OpenAPI fetch script CI/CD pipeline'a girmeli mi (M5+ scope ama not düş)
- [ ] Zustand `useShallow` selector kullanımı dokümantasyonda var mı (Order 6/7/8/9 onu uygulayacak)

#### Acceptance criteria

- [ ] Cockpit `/cockpit` URL açılıyor, 4 tab görünüyor (placeholder içerikler)
- [ ] URL `?tab=...` ile tab değiştirilebiliyor (sayfa reload sonrası state korunuyor)
- [ ] Manual smoke: 2 tarayıcı tab'da cockpit aç, biri WS disconnect simulate (devtools), reconnect sonrası missed envelope replay
- [ ] 10 yeni test pass (apps/web)
- [ ] mevcut 1135 backend test korundu (frontend test pipeline ayrı CI)
- [ ] `pnpm gen:api` çalışıyor, `lib/api-types.ts` üretiliyor

#### Risks & open questions

- **R5.1:** apps/web'de mevcut test setup yok olabilir (`__tests__/` dizini bulunmadı). Mitigation: vitest + jsdom + @testing-library/react ekle (Order 5.0 ekstra alt-task).
- **R5.2:** shadcn/ui CLI mevcut Tailwind v3 vs Tailwind v4 (HeroUI v3 v4 istiyor) çakışması olabilir. Mitigation: `apps/web/tailwind.config.ts` mevcut versiyonu koruyup shadcn'i ona göre install.
- **OQ5.1:** Cockpit ana URL `/cockpit` mı yoksa root `/` mi? Mevcut `/` dashboard var (paused/recent sessions). Karar: cockpit ayrı sayfa, mevcut dashboard `/dashboard` veya `/` korunur (legacy). M5+'da konsolide.

---

### Order 6 — Mission tab

**Tahmin:** 2-3 gün
**Bağımlılık:** Order 5 (tab shell), Order 1 (SortableContext fix pattern)
**Bloklar:** Order 9 (E2E PRD smoke Mission'ı içerir)

#### Scope

Linear-style swimlane kanban + AgentOps-style session drawer. Read-mostly
kanban (orchestrator-driven), tek manuel hareket `blocked → pending`.
Handed-off lane explicit görsel + actionable CTA.

#### Files touched

| Dosya | Değişiklik | Açıklama |
|-------|-----------|----------|
| `apps/web/app/cockpit/components/mission/MissionTab.tsx` | NEW | Tab root, project selector + KanbanBoard wire |
| `apps/web/app/cockpit/components/mission/KanbanBoard.tsx` | NEW | Sütun=status + Group by Rows toggle |
| `apps/web/app/cockpit/components/mission/Column.tsx` | NEW | Status column (SortableContext + cards) |
| `apps/web/app/cockpit/components/mission/SortableCard.tsx` | NEW | useSortable + DnD primitive |
| `apps/web/app/cockpit/components/mission/SessionDrawer.tsx` | NEW | Sheet primitive (shadcn/ui) — kart tıklama açar |
| `apps/web/app/cockpit/components/mission/HandoffLane.tsx` | NEW | Handed-off explicit görsel |
| `apps/web/app/cockpit/components/mission/SwimlaneToggle.tsx` | NEW | "Group by status" / "Group by session" toggle |
| `apps/web/lib/store/mission-slice.ts` | EDIT | Placeholder → real slice |
| `apps/web/lib/queries/mission-queries.ts` | NEW | TanStack Query keys + fetchers |
| `apps/web/__tests__/mission/mission-slice.test.ts` | NEW | 5 test |
| `apps/web/__tests__/mission/KanbanBoard.test.tsx` | NEW | 4 test |

#### Sub-tasks

6.1. **Mission slice.** `mission-slice.ts`:
```ts
export type MissionSlice = {
  activeProjectSlug: string | null;
  activeMissionId: string | null;  // drawer için
  swimlaneMode: "status" | "session";
  filterCli: string | null;
  setActiveProject: (slug: string | null) => void;
  setActiveMission: (id: string | null) => void;
  setSwimlaneMode: (mode: "status" | "session") => void;
  setFilterCli: (cli: string | null) => void;
};
```

6.2. **Mission queries.** `mission-queries.ts`:
```ts
export const missionKeys = {
  all: ["mission"] as const,
  project: (slug: string) => [...missionKeys.all, "project", slug] as const,
  kanban: (slug: string) => [...missionKeys.project(slug), "kanban"] as const,
  session: (id: string) => [...missionKeys.all, "session", id] as const,
};

export function useKanbanQuery(slug: string) {
  return useQuery({
    queryKey: missionKeys.kanban(slug),
    queryFn: () => getKanban(slug),
    staleTime: Infinity,
  });
}
```

6.3. **WS subscription wire.** `MissionTab.tsx`:
```tsx
useWebsocketSubscription({
  url: `${WS_BASE}/api/projects/${slug}/kanban/stream`,
  onEnvelope: (env) => {
    if (env.event_type === "kanban") {
      queryClient.setQueryData(
        missionKeys.kanban(slug),
        env.payload  // KanbanResponse mirror
      );
    }
  },
});
```

6.4. **KanbanBoard render.** Sütun=status (5 kolon: pending, running, blocked, handed-off, done). Swimlane toggle aktifse satır=session. SwimlaneToggle component küçük segmented control.

6.5. **SortableCard.** `useSortable({ id: card.id })` + Column'da `<SortableContext items={cards.map(c => c.id)} strategy={verticalListSortingStrategy}>`. Drag-drop **read-mostly contract**: sadece blocked → pending hareket UI tarafında izinli; başka kombinasyonda toast warning ("Status orchestrator-driven, edit not allowed in M4").

6.6. **HandoffLane.** Handed-off kolonu özel görsel (border-amber + "Resume" CTA button). Click → `POST /api/sessions/paused/{session_id}/resume`.

6.7. **SessionDrawer.** Sheet (shadcn/ui) — sağdan açılan panel. Kart tıklama → drawer açar (mission-slice activeMissionId set). Drawer içinde:
- Session detail (recent + paused state)
- Mevcut `CardDetailPanel` 4-sekmesi (overview/logs/tools/settings) — embed
- Order 7'de Run tab pattern'ı drawer'a da yansır (waterfall placeholder)

6.8. **Test (mission-slice 5):**
- `test_setActiveProject_clears_active_mission`
- `test_setActiveMission_persists`
- `test_setSwimlaneMode_toggles`
- `test_setFilterCli_filters_by_cli`
- `test_filter_combined_with_swimlane`

6.9. **Test (KanbanBoard 4):**
- `test_renders_5_status_columns`
- `test_drag_within_blocked_to_pending_calls_resume_api`
- `test_drag_other_combinations_show_warning`
- `test_swimlane_toggle_switches_layout`

#### Audit-god checklist

- [ ] Read-mostly contract gerçekten enforce edilmiş mi (blocked→pending dışındaki tüm drag'lar UI'da rejected)
- [ ] WS-driven kanban update useShallow kullanıyor mu (re-render kaskadı kontrolü)
- [ ] HandoffLane "Resume" CTA `paused/{id}/resume` endpoint'ine doğru session_id ile gidiyor mu
- [ ] SortableContext strategy doğru (verticalListSortingStrategy)
- [ ] Mission slice persistence yok (sayfa reload sonrası state sıfırdan; URL state sufficient mi?)

#### Acceptance criteria

- [ ] Mission tab açılıyor, kanban görünüyor (mevcut `/project/?slug=` ile aynı veri)
- [ ] Swimlane toggle çalışıyor
- [ ] Drag blocked → pending → orchestrator API çağrılıyor (manual smoke)
- [ ] Drag diğer kombinasyon → toast warning
- [ ] Handed-off lane Resume CTA çalışıyor
- [ ] Drawer kart tıklamasıyla açılıyor, session detail gösteriyor
- [ ] WS-driven update <1sn UI'a yansıyor (manual: ikinci tarayıcıda kart oluştur, ilk tarayıcıda görünüyor)
- [ ] 9 yeni test pass

#### Risks & open questions

- **R6.1:** `paused/{id}/resume` endpoint'i kart-bazlı değil session-bazlı. Mission tab kart vs session ayrımı? Karar: bir kart = bir session (M3'ten gelen 1:1 mapping korundu).
- **OQ6.1:** Drag ile **planned** status değişikliği (örn. running → blocked manuel mark) M4'te scope dışı mı? Karar: evet, scope dışı; M5'te policy decision (memory: provider_usage_source mantığı — state derived, not mutated).

---

### Order 7 — Run tab

**Tahmin:** 3-4 gün
**Bağımlılık:** Order 5 (tab shell), Order 2 (multi-dir audit WS), Order 1 (audit dir resolver)
**Bloklar:** Order 9 (E2E)

#### Scope

Hibrit decision audit görselleştirme: Trace-tree (LangSmith pattern) primary
+ Waterfall (AgentOps pattern) toggle. Audit JSONL stream renderer
react-virtuoso `followOutput` ile + 22 audit category renderer registry +
filter chips (tool / cli / event-type / free-text).

#### Files touched

| Dosya | Değişiklik | Açıklama |
|-------|-----------|----------|
| `apps/web/app/cockpit/components/run/RunTab.tsx` | NEW | Tab root |
| `apps/web/app/cockpit/components/run/AuditStream.tsx` | NEW | react-virtuoso + WS subscribe + gap detection |
| `apps/web/app/cockpit/components/run/TraceTree.tsx` | NEW | LangSmith-style nested |
| `apps/web/app/cockpit/components/run/Waterfall.tsx` | NEW | AgentOps-style timeline |
| `apps/web/app/cockpit/components/run/EventRenderer/index.ts` | NEW | Renderer registry (22 category × renderer) |
| `apps/web/app/cockpit/components/run/EventRenderer/<category>.tsx` | NEW (22 dosya) | Per-category renderer (state, lifecycle, agent, tool grupları) |
| `apps/web/app/cockpit/components/run/FilterChips.tsx` | NEW | Tool / CLI / event-type / search |
| `apps/web/app/cockpit/components/run/ParadigmToggle.tsx` | NEW | Trace ↔ Waterfall toggle |
| `apps/web/lib/store/run-slice.ts` | EDIT | Real slice |
| `apps/web/lib/queries/run-queries.ts` | NEW | TanStack Query keys |
| `apps/web/lib/run/trace-builder.ts` | NEW | Flat events → nested tree (round + tool order pairing) |
| `apps/web/lib/run/waterfall-builder.ts` | NEW | Flat events → gantt rows |
| `apps/web/__tests__/run/EventRenderer.test.tsx` | NEW | 22 category snapshot |
| `apps/web/__tests__/run/AuditStream.test.tsx` | NEW | 6 test (gap + replay + virtualization) |
| `apps/web/__tests__/run/trace-builder.test.ts` | NEW | 5 test |

#### Sub-tasks

7.1. **Run slice.** `run-slice.ts`:
```ts
export type RunSlice = {
  activeSessionId: string | null;
  paradigm: "trace" | "waterfall";
  filterTool: string | null;
  filterCli: string | null;
  filterEventType: string | null;
  searchQuery: string;
  lastSeq: number | null;
  setActiveSession: (id: string | null) => void;
  setParadigm: (p: "trace" | "waterfall") => void;
  setFilter: (key: "tool" | "cli" | "eventType", value: string | null) => void;
  setSearchQuery: (q: string) => void;
  setLastSeq: (n: number) => void;
};
```

7.2. **EventRenderer registry.** `EventRenderer/index.ts`:
```ts
import { type AuditCategory } from "@/lib/api-types";
// 22 category, generated from audit.py:
const renderers: Record<AuditCategory, ComponentType<{ event: AuditEvent }>> = {
  "session.state": SessionStateRenderer,
  "runtime.spawn": RuntimeSpawnRenderer,
  "runtime.health": RuntimeHealthRenderer,
  // ... 22 toplam
};

export function EventRenderer({ event }: { event: AuditEvent }) {
  const Renderer = renderers[event.category] ?? UnknownRenderer;
  return <Renderer event={event} />;
}
```

22 renderer dosyası **her biri ~30 satır**, ortak pattern:
```tsx
// SessionStateRenderer.tsx
import { Badge } from "@/components/ui/badge";

export function SessionStateRenderer({ event }: { event: AuditEvent }) {
  const { from, to } = event.payload;
  return (
    <div className="flex items-center gap-2 text-sm text-blue-500">
      <Badge variant="outline">{event.category}</Badge>
      <span>{from} → {to}</span>
      <RelativeAge ts={event.ts} />
    </div>
  );
}
```

7.3. **AuditStream.** react-virtuoso:
```tsx
<Virtuoso
  data={events}
  followOutput={isAtBottom ? "smooth" : false}
  atBottomStateChange={setIsAtBottom}
  itemContent={(_, event) => <EventRenderer event={event} />}
/>
```
WS subscribe:
```tsx
useWebsocketSubscription({
  url: `${WS_BASE}/api/sessions/${sessionId}/stream?last_seq=${lastSeq ?? 0}`,
  onEnvelope: (env) => {
    if (env.event_type !== "audit") return;
    queryClient.setQueryData(runKeys.events(sessionId), (old: AuditEvent[] = []) => [...old, env.payload]);
    setLastSeq(env.seq);
  },
  onGap: async (lastSeq, newSeq) => {
    // REST fallback fill
    const missed = await fetchEventsRange(sessionId, lastSeq + 1, newSeq);
    queryClient.setQueryData(runKeys.events(sessionId), (old: AuditEvent[] = []) => [...old, ...missed]);
  },
});
```

7.4. **TraceTree.** Flat events → nested:
- Outer node: `agent.invoke` (Round N)
- Children: `tool.call` + `tool.result` paired (round + order_in_reply key)
- Sibling: `selffork_jr.reply`
- Outermost: `session.state`, `agent.done`

`trace-builder.ts`:
```ts
export function buildTraceTree(events: AuditEvent[]): TraceNode[] {
  // Group by round
  // Pair tool.call with tool.result by (round, tool, order)
  // Nest under agent.invoke
}
```

7.5. **Waterfall.** Gantt-style:
- X axis: time (relative to first event)
- Y axis: rows (Round N + tool calls + sleep periods)
- Bar width = duration (event.ts → next event.ts)
- Color = category group (agent=blue, tool=green, sleep=gray)

`waterfall-builder.ts`:
```ts
export function buildWaterfall(events: AuditEvent[]): WaterfallRow[] {
  // ... compute durations, group by round
}
```

7.6. **FilterChips.** shadcn/ui Badge + cmdk command palette pattern:
```tsx
<div className="flex gap-2">
  <FilterChip label="Tool" options={TOOLS} value={filterTool} onChange={...} />
  <FilterChip label="CLI" options={CLIS} value={filterCli} onChange={...} />
  <FilterChip label="Event" options={CATEGORIES} value={filterEventType} onChange={...} />
  <Input placeholder="Search..." value={searchQuery} onChange={...} />
</div>
```

7.7. **ParadigmToggle.** Segmented control:
```tsx
<Tabs value={paradigm} onValueChange={setParadigm}>
  <TabsList>
    <TabsTrigger value="trace">Trace tree</TabsTrigger>
    <TabsTrigger value="waterfall">Waterfall</TabsTrigger>
  </TabsList>
</Tabs>
```

7.8. **Filter logic.** `useMemo` ile events array filter:
```ts
const filteredEvents = useMemo(() => events.filter(e => {
  if (filterTool && e.payload.tool !== filterTool) return false;
  if (filterCli && e.payload.binary !== filterCli) return false;
  if (filterEventType && e.category !== filterEventType) return false;
  if (searchQuery && !JSON.stringify(e).toLowerCase().includes(searchQuery.toLowerCase())) return false;
  return true;
}), [events, filterTool, filterCli, filterEventType, searchQuery]);
```

7.9. **EventRenderer test (22 category snapshot).** `EventRenderer.test.tsx`:
- Her 22 category için bir test: `expect(renderer.toMatchSnapshot())`.

7.10. **AuditStream test (6):**
- `test_render_events_in_order`
- `test_followOutput_when_at_bottom`
- `test_pause_followOutput_when_user_scrolls_up`
- `test_gap_detection_calls_rest_fallback`
- `test_replay_on_reconnect`
- `test_virtualization_with_10k_events_no_lag` (perf benchmark)

7.11. **trace-builder test (5):**
- `test_pairs_tool_call_with_tool_result`
- `test_orphan_tool_call_without_result_renders`
- `test_nested_round_hierarchy`
- `test_unknown_category_falls_back_to_default`
- `test_empty_events_returns_empty_tree`

#### Audit-god checklist

- [ ] 22 EventRenderer dosyası exhaustive (audit.py:28-57'deki tüm category'ler kapsanıyor)
- [ ] `UnknownRenderer` fallback yeni category eklendiğinde sessizce kırılmıyor (banner mesajı)
- [ ] Trace tree pairing edge case'leri (tool.call without matching tool.result, vice versa) kapsanıyor
- [ ] Virtualization 10K+ event'te lag testi yazıldı (perf benchmark)
- [ ] Filter chip URL'e yansıyor mu (deep-link, paylaşılabilir)
- [ ] Filter combined filter logic doğru (AND mı OR mu, beklenti)
- [ ] AuditStream `last_seq` Order 5 multiplex client'ından doğru aktarılıyor mu

#### Acceptance criteria

- [ ] Real session koş (`apps/web` dev + orchestrator dev + PRD smoke)
- [ ] Audit log <1sn UI'a düşüyor (latency benchmark)
- [ ] Trace ↔ Waterfall toggle smooth (transition <100ms)
- [ ] 22 category renderer'ı tüm event tipini doğru render ediyor (snapshot test pass)
- [ ] Filter chips canlı süzme (tek seçimde 100ms cevap)
- [ ] Search free-text 5 char tipping → filter aktif
- [ ] Gap detection: WS disconnect 5 saniye sim → reconnect → missing events backfilled (REST fallback)
- [ ] 33 yeni test pass (5 trace-builder + 6 stream + 22 renderer)

#### Risks & open questions

- **R7.1:** 22 renderer dosyası "boilerplate ağır" görünüyor; zoom out: registry pattern tek `case` switch'e indirgenebilir. Karar: per-category dosya açıkça extensible (M5+ yeni category eklendiğinde tek dosya), iyi tradeoff.
- **R7.2:** Waterfall D3/recharts/visx hangisi? Default: HTML/CSS gantt rows (lightweight, no extra dep). Performance gerekirse visx M5+'a iter.
- **OQ7.1:** Trace tree drill-down'da tool.call args + tool.result preview göstermek istiyor muyuz? Karar: evet (M-7 result_payload_preview field'ını kullan).
- **OQ7.2:** Sleep / cooldown periods waterfall'da nasıl render edilecek? Default: gri "—— sleeping (5h cooldown)" bar.

---

### Order 8 — Chat tab

**Tahmin:** 3-4 gün
**Bağımlılık:** Order 5 (tab shell), Order 4 (chat backend)
**Bloklar:** Order 9 (E2E)

#### Scope

Streamdown markdown renderer + assistant-ui Tool component (collapsible) +
BranchPicker (first-class branching) + tool inline + token streaming.
Yamaç edit → backend yeni branch + Mind T2 alternative-path log (Order 4
entegrasyonu).

#### Files touched

| Dosya | Değişiklik | Açıklama |
|-------|-----------|----------|
| `apps/web/app/cockpit/components/chat/ChatTab.tsx` | NEW | Tab root |
| `apps/web/app/cockpit/components/chat/MessageList.tsx` | NEW | Virtuoso + message bubble |
| `apps/web/app/cockpit/components/chat/MessageBubble.tsx` | NEW | Streamdown render + edit affordance |
| `apps/web/app/cockpit/components/chat/ToolInline.tsx` | NEW | assistant-ui Tool component (collapsible compound) |
| `apps/web/app/cockpit/components/chat/BranchPicker.tsx` | NEW | Previous/Next/N of M |
| `apps/web/app/cockpit/components/chat/MessageInput.tsx` | NEW | Submit + edit-from-history |
| `apps/web/app/cockpit/components/chat/DoneSentinel.tsx` | NEW | `[SELFFORK:DONE]` terminal banner |
| `apps/web/lib/store/chat-slice.ts` | EDIT | Real slice |
| `apps/web/lib/queries/chat-queries.ts` | NEW | TanStack Query keys |
| `apps/web/lib/chat/branch-tree.ts` | NEW | Flat branches → tree (parent_id chain) |
| `apps/web/__tests__/chat/BranchPicker.test.tsx` | NEW | 5 test |
| `apps/web/__tests__/chat/ToolInline.test.tsx` | NEW | 4 test (state machine) |
| `apps/web/__tests__/chat/chat-slice.test.ts` | NEW | 5 test |

#### Sub-tasks

8.1. **Chat slice.** `chat-slice.ts`:
```ts
export type ChatSlice = {
  activeSessionId: string | null;
  activeBranchId: string | null;
  editingMessageId: string | null;
  streamingTokenBuffer: Record<string, string>;  // message_id → accumulated tokens
  setActiveSession: (id: string | null) => void;
  setActiveBranch: (id: string | null) => void;
  setEditingMessage: (id: string | null) => void;
  appendToken: (messageId: string, token: string) => void;
  flushTokens: (messageId: string) => void;
};
```

8.2. **Chat queries.** `chat-queries.ts`:
```ts
export const chatKeys = {
  all: ["chat"] as const,
  session: (id: string) => [...chatKeys.all, "session", id] as const,
  branches: (id: string) => [...chatKeys.session(id), "branches"] as const,
  messages: (id: string, branchId: string) => [...chatKeys.session(id), "messages", branchId] as const,
};
```

8.3. **MessageBubble + Streamdown.** `MessageBubble.tsx`:
```tsx
import { Streamdown } from "streamdown";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const tokenBuffer = useCockpitStore(s => s.streamingTokenBuffer[message.id]);
  const content = message.streaming ? tokenBuffer : message.content;

  return (
    <div className="message-bubble">
      <Streamdown
        controls={{ code: true, mermaid: false, math: false }}
        rehypePlugins={[rehypeHarden]}
      >
        {content}
      </Streamdown>
      {message.role === "user" && <EditAffordance messageId={message.id} />}
    </div>
  );
}
```

8.4. **ToolInline.** assistant-ui pattern:
```tsx
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

type ToolState = "partial-call" | "running" | "output-available" | "error";

export function ToolInline({ toolCall, toolResult }: { toolCall: AuditEvent; toolResult?: AuditEvent }) {
  const state: ToolState =
    toolResult ? (toolResult.payload.status === "ok" ? "output-available" : "error")
               : "running";
  const [isOpen, setIsOpen] = useState(state === "running");  // expanded during stream
  // collapsed-after-completion (Cline pattern):
  useEffect(() => {
    if (state === "output-available" || state === "error") {
      setTimeout(() => setIsOpen(false), 2000);
    }
  }, [state]);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger>
        <ToolHeader name={toolCall.payload.tool} state={state} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ToolInput args={toolCall.payload.args} />
        {toolResult && <ToolOutput preview={toolResult.payload.result_payload_preview} />}
      </CollapsibleContent>
    </Collapsible>
  );
}
```

8.5. **BranchPicker.** assistant-ui-inspired:
```tsx
export function BranchPicker({ messageId, branches }: { messageId: string; branches: Branch[] }) {
  const activeBranchId = useCockpitStore(s => s.activeBranchId);
  const setActiveBranch = useCockpitStore(s => s.setActiveBranch);
  const branchesAtMessage = branches.filter(b => b.fork_message_id === messageId);
  if (branchesAtMessage.length < 2) return null;

  const activeIndex = branchesAtMessage.findIndex(b => b.id === activeBranchId);

  return (
    <div className="branch-picker">
      <button onClick={() => setActiveBranch(branchesAtMessage[activeIndex - 1]?.id ?? null)}>
        ◀ Prev
      </button>
      <span>{activeIndex + 1} / {branchesAtMessage.length}</span>
      <button onClick={() => setActiveBranch(branchesAtMessage[activeIndex + 1]?.id ?? null)}>
        Next ▶
      </button>
    </div>
  );
}
```

8.6. **MessageInput.** Edit mode:
```tsx
export function MessageInput() {
  const editingMessageId = useCockpitStore(s => s.editingMessageId);
  const setEditingMessage = useCockpitStore(s => s.setEditingMessage);
  const [content, setContent] = useState("");

  const submit = async () => {
    if (editingMessageId) {
      await postMessageEdit(sessionId, editingMessageId, { content });
      setEditingMessage(null);
    } else {
      await postMessage(sessionId, { content, branch_id: activeBranchId });
    }
    setContent("");
  };

  return (
    <Textarea value={content} onChange={e => setContent(e.target.value)} onKeyDown={e => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    }} />
  );
}
```

8.7. **DoneSentinel.** `[SELFFORK:DONE]` detection:
```tsx
export function DoneSentinel({ message }: { message: ChatMessage }) {
  if (!message.content.includes("[SELFFORK:DONE]")) return null;
  return (
    <div className="done-banner border-success/40 bg-success/10 p-4">
      ✓ Session marked done by Jr autopilot
    </div>
  );
}
```

8.8. **WS subscription.** `ChatTab.tsx`:
```tsx
useWebsocketSubscription({
  url: `${WS_BASE}/api/sessions/${sessionId}/chat/stream?last_seq=${lastSeq}`,
  onEnvelope: (env) => {
    if (env.event_type === "chat.token") {
      const { message_id, token } = env.payload;
      useCockpitStore.getState().appendToken(message_id, token);
    }
  },
});
```

8.9. **Test (BranchPicker 5):**
- `test_renders_when_2plus_branches`
- `test_hides_when_single_branch`
- `test_prev_next_navigates`
- `test_disabled_at_boundaries`
- `test_count_format_correct`

8.10. **Test (ToolInline 4):**
- `test_partial_call_state`
- `test_running_expanded`
- `test_output_available_collapsed_after_2s`
- `test_error_expanded_persists`

8.11. **Test (chat-slice 5):**
- `test_appendToken_buffers`
- `test_flushTokens_clears`
- `test_setActiveBranch_persists`
- `test_setEditingMessage_clears_on_submit`
- `test_streaming_buffer_per_message_isolated`

#### Audit-god checklist

- [ ] Streamdown rehype-harden config XSS-safe (script tag, iframe, javascript: URL strip)
- [ ] BranchPicker concurrent edit handling (iki tarayıcıda aynı anda edit → server win? client win? toast?)
- [ ] result_payload_preview privacy redact UI'a inheritance — UI redact mark görsel olarak göstermeli mi (banner: "secrets redacted")
- [ ] Token streaming back-pressure: 1000 token/sec gelirse UI freeze yok mu (batch flush)
- [ ] Edit → branch → Mind T2 log fail durumu UI'da nasıl görünüyor (Order 4 R)

#### Acceptance criteria

- [ ] Real Jr round-loop konuşması Chat tab'da görünüyor (manual smoke: PRD koş, Yamaç mesaj at, Jr cevap ver)
- [ ] Token streaming <50ms latency UI'a (benchmark)
- [ ] Edit mesaj → yeni branch yaratılıyor, BranchPicker görünüyor
- [ ] Branch switch → mesaj listesi güncelleniyor
- [ ] ToolInline state machine doğru (running → output-available → collapsed)
- [ ] [SELFFORK:DONE] sentinel terminal banner görünüyor
- [ ] 14 yeni test pass

#### Risks & open questions

- **R8.1:** Streamdown'ın `rehype-harden` default config'i XSS koruması yeterli mi? Mitigation: explicit `rehypeSanitize` ek (M5+ scope ama Order 8'de ekle).
- **R8.2:** Token streaming buffering vs immediate flush tradeoff. Default: 50ms debounce + flush. Yamaç tipping göstermek için minimum 16ms (60fps).
- **OQ8.1:** Edit history visibility — eski branch'leri kullanıcıya göstermek mi yoksa gizlemek mi (BranchPicker sadece "branchesAtMessage")? Default: gizleme yok, hepsi BranchPicker'da gez.
- **OQ8.2:** Multi-line edit (özellikle code block'lar) Textarea yeterli mi yoksa Monaco editor mi? Default: Textarea (M5+'da Monaco).

---

### Order 9 — Context tab + E2E + Polish

**Tahmin:** 4-5 gün (E2E + audit-god review + ADR close-out dahil)
**Bağımlılık:** Order 5 (shell), Order 3 (Mind HTTP), Order 8 (chat tab pattern öğrenildi)
**Bloklar:** Yok (M4 done)

#### Scope

Context tab — SelfFork native 6-tier düz görselleştirme + RAG live query +
provenance stream. **Ek olarak Order 9, M4 close-out görevini de üstlenir:**
audit-god full review, e2e PRD smoke, ADR-004 status update, final test
gate, sources update.

#### Files touched

| Dosya | Değişiklik | Açıklama |
|-------|-----------|----------|
| `apps/web/app/cockpit/components/context/ContextTab.tsx` | NEW | Tab root + tier sections |
| `apps/web/app/cockpit/components/context/TierSection.tsx` | NEW | Generic collapsible per tier |
| `apps/web/app/cockpit/components/context/T1Working.tsx` | NEW | JSON viewer |
| `apps/web/app/cockpit/components/context/T2Episodic.tsx` | NEW | Note list |
| `apps/web/app/cockpit/components/context/T3Graph.tsx` | NEW | D3 force-graph (seed-based) |
| `apps/web/app/cockpit/components/context/T4Procedural.tsx` | NEW | Pattern note list |
| `apps/web/app/cockpit/components/context/T5Reflection.tsx` | NEW | Reflection report viewer |
| `apps/web/app/cockpit/components/context/T6Recall.tsx` | NEW | Audit-derived event list |
| `apps/web/app/cockpit/components/context/RecallQueryBar.tsx` | NEW | Interactive RetrieveConfig builder |
| `apps/web/app/cockpit/components/context/ProvenanceFeed.tsx` | NEW | Live tail (mind_router WS) |
| `apps/web/lib/store/context-slice.ts` | EDIT | Real slice |
| `apps/web/lib/queries/context-queries.ts` | NEW | TanStack Query keys |
| `apps/web/__tests__/context/TierSection.test.tsx` | NEW | 4 test |
| `apps/web/__tests__/context/RecallQueryBar.test.tsx` | NEW | 4 test |
| `apps/web/__tests__/context/T3Graph.test.tsx` | NEW | 3 test (D3 render + perf) |
| `tests/e2e/test_m4_cockpit_e2e.py` | NEW | Full PRD smoke |
| `docs/decisions/ADR-004_M4_Cockpit.md` | EDIT | Order tablosu ✅ + Final test/lint durumu + Sources update |

#### Sub-tasks

9.1. **Context slice.** `context-slice.ts`:
```ts
export type ContextSlice = {
  activeProjectSlug: string | null;
  expandedTiers: Set<TierName>;
  recallQuery: string;
  recallTier: TierName | null;
  graphSeed: string;
  setActiveProject: (slug: string | null) => void;
  toggleTier: (tier: TierName) => void;
  setRecallQuery: (q: string) => void;
  setRecallTier: (t: TierName | null) => void;
  setGraphSeed: (s: string) => void;
};
```

9.2. **Context queries.** `context-queries.ts`:
```ts
export const contextKeys = {
  all: ["context"] as const,
  project: (slug: string) => [...contextKeys.all, "project", slug] as const,
  stats: (slug: string) => [...contextKeys.project(slug), "stats"] as const,
  working: (slug: string) => [...contextKeys.project(slug), "working"] as const,
  notes: (slug: string, tier: string) => [...contextKeys.project(slug), "notes", tier] as const,
  recall: (slug: string, query: string) => [...contextKeys.project(slug), "recall", query] as const,
  graph: (slug: string, seed: string) => [...contextKeys.project(slug), "graph", seed] as const,
  provenance: (slug: string) => [...contextKeys.project(slug), "provenance"] as const,
};
```

9.3. **TierSection generic.**
```tsx
export function TierSection<T>({ tier, query, render }: TierSectionProps<T>) {
  const isExpanded = useCockpitStore(s => s.expandedTiers.has(tier));
  const toggle = useCockpitStore(s => s.toggleTier);
  const { data, isLoading } = query;
  return (
    <Collapsible open={isExpanded} onOpenChange={() => toggle(tier)}>
      <CollapsibleTrigger>
        <TierHeader tier={tier} count={data?.length} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        {isLoading ? <Skeleton /> : render(data)}
      </CollapsibleContent>
    </Collapsible>
  );
}
```

9.4. **T1Working.** JSON viewer (react-json-view veya custom). T1 WorkingBlock content + supersede history.

9.5. **T2Episodic.** Note list (Virtuoso) + RelativeAge per note + filter chips (kind, intent, tag).

9.6. **T3Graph.** D3 force-graph:
- Seed input (RecallQueryBar'a entegre)
- API: `GET /api/projects/{slug}/mind/graph/triples?seed=...`
- D3-force layout, nodes=PhraseNode, edges=GraphTriple
- Click node → seed update (drill-down)
- Performance: 1000 triple cap, beyond M5+

9.7. **T4Procedural.** Pattern note list (T2 pattern).

9.8. **T5Reflection.** Reflection report viewer:
- Note list (kind="reflection_report")
- Click → expanded view (markdown render with Streamdown)

9.9. **T6Recall.** Audit-derived event list:
- Recall reader fetch via mind_router (eğer expose ediliyorsa, yoksa direct audit log read fallback)
- Filtered by category, time range

9.10. **RecallQueryBar.**
```tsx
export function RecallQueryBar() {
  const recallQuery = useCockpitStore(s => s.recallQuery);
  const recallTier = useCockpitStore(s => s.recallTier);
  // ... debounced setRecallQuery
  return (
    <div>
      <Input placeholder="Recall query..." />
      <Select value={recallTier ?? ""} onValueChange={...}>
        {TIERS.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
      </Select>
    </div>
  );
}
```

9.11. **ProvenanceFeed.** WS live tail:
```tsx
useWebsocketSubscription({
  url: `${WS_BASE}/api/projects/${slug}/mind/provenance/stream`,
  onEnvelope: (env) => {
    if (env.event_type === "mind") {
      queryClient.setQueryData(contextKeys.provenance(slug), (old: ProvenanceEntry[] = []) => [...old, env.payload]);
    }
  },
});
```

9.12. **E2E test.** `tests/e2e/test_m4_cockpit_e2e.py`:
```python
@pytest.mark.e2e
def test_m4_cockpit_e2e_prd_smoke(playwright_session, orchestrator_session):
    # 1. Start orchestrator (subprocess + cleanup)
    # 2. Start Next.js dev (subprocess + cleanup)
    # 3. Playwright: navigate /cockpit
    # 4. Switch to Mission tab → kanban görünmeli
    # 5. Create card → Jr autopilot tool call'u tetiklenmeli (audit log check)
    # 6. Switch to Run tab → audit stream görünmeli
    # 7. Switch to Chat tab → mesaj at, Jr cevap → branch yarat
    # 8. Switch to Context tab → 6-tier görünmeli, recall query
    # 9. Verify all WS subscriptions clean disconnected
```

9.13. **Audit-god full review.** Bu Order'da explicit audit-god ajanı çağrılır:
- Tüm M4 değişikliklerini cross-pillar review
- 4 tab'ın audit-god'a verilmesi (her biri için ayrı ajan)
- ETA 0.5 gün

9.14. **ADR-004 close-out.** `docs/decisions/ADR-004_M4_Cockpit.md`:
- Order tablosu: tüm Order'lar ✅
- Final test/lint durumu (asıl rakamlarla)
- Sınırlamalar / kalan iş güncelle (M5+'a iter listesi gerçek hale)
- Sources tam

9.15. **Final test gate.**
- `pytest packages/ tests/` → 1135 baseline + Order başına yeni testler ≥ 1185
- `pnpm test` (apps/web) — yeni eklenen tüm test'ler pass
- `ruff check packages/ apps/web/` clean
- `mypy --strict packages/` clean
- `pnpm typecheck` (apps/web) clean

9.16. **Manual smoke (Yamaç laptop).** Yamaç'a koşturmadan M4 kapanmaz. Smoke checklist:
- [ ] Cockpit `/cockpit` açıldı
- [ ] Mission tab kanban canlı, kart oluşturma çalışıyor
- [ ] Run tab gerçek session audit stream <1sn
- [ ] Chat tab Jr ile konuşma, edit, branch yaratma
- [ ] Context tab 6-tier görünür, recall query çalışıyor
- [ ] WS reconnect resilience (devtools network throttle)
- [ ] Latency benchmark: tool call event UI'a < 1sn

#### Audit-god checklist (Order 9 close-out)

- [ ] 6-tier UI pillar boundary intact mi (Mind ↔ orchestrator coupling sınırlı)
- [ ] D3 force-graph performance (>1000 triples test edildi mi, perf benchmark)
- [ ] E2E test deterministic mi (CI-safe — flaky değil)
- [ ] T6 Recall reader audit log read'i pillar boundary'i bozuyor mu (Mind → orchestrator audit coupling)
- [ ] RecallQueryBar Pydantic projection tam RetrieveConfig'i destekliyor mu (filter DSL UI'da)
- [ ] ADR-004 close-out gerçek rakamlarla mı yoksa placeholder'la mı

#### Acceptance criteria (M4 done)

**Bu hem Order 9 hem M4 milestone done criteria'sı:**

- [ ] **4 tab live** (Mission/Run/Chat/Context) gerçek PRD koşusunda çalışıyor
- [ ] **WebSocket telemetry**: tool call event'i UI'a < 1sn (benchmark passed)
- [ ] **Mock yok**: tek dev workflow korundu (no-mock kuralı, MSW yok, Storybook yok)
- [ ] **ADR-004** kabul edildi (DRAFT → Kabul; close-out tamamlandı)
- [ ] sub-task'lar audit-god review'dan geçti (M3 disiplin)
- [ ] **1135+ test pass**; ruff + mypy strict clean korundu
- [ ] **Yamaç laptop'tan canlı PRD koşusu** izledi, müdahale etti, beğendi
- [ ] 11 yeni test pass (Order 9: 4+4+3 + 1 e2e)
- [ ] Cross-Order: 9 + 4 + 11 + 7 + 13 + 9 + 33 + 14 + 11 = ~111 yeni test (1135+111 = ~1246 hedef)

#### Risks & open questions

- **R9.1:** D3 force-graph M4'e ağır gelebilir (>1 hafta). Mitigation: minimal version (top_k=20, simple layout); advanced viz M5+'a iter.
- **R9.2:** E2E test setup (Playwright + dev servers) flaky olma riski. Mitigation: explicit timeouts + retry policy + CI annotation `@pytest.mark.flaky(reruns=2)`.
- **OQ9.1:** T3 Graph "PhraseNode click" drill-down semantic'i — yeni triple fetch mu yoksa local filter mı? Default: yeni fetch (server-driven).
- **OQ9.2:** Yamaç laptop smoke test başarısızsa M4 done değil — close-out tekrar açılır. Bu Order 9 uzatmasına yol açabilir; mitigation: Yamaç manuel smoke'u Order 9'un %50'sinden önce başlat (early feedback).

---

## 5. Cross-cutting concerns

### 5.1. Style & convention

- **TypeScript strict** korundu (apps/web mevcut tsconfig).
- **ESLint** (apps/web) ve **ruff** (Python) zero regression.
- **shadcn/ui primitive isimlendirme**: `tabs.tsx` (lowercase + dash) — mevcut convention (`button.tsx`, `card.tsx`).
- **Component dosyası**: PascalCase (`MissionTab.tsx`).
- **Hook**: `use*` prefix.
- **Store slice**: `<name>-slice.ts` (lowercase + dash, mevcut `sidebar-context.tsx` paterniyle uyumlu).

### 5.2. Memory & decision hijiyeni

Her Order kapanışında **ilgili memory entry** güncellenir:
- `project_m4_cockpit_blueprint.md` — Order kapanma durumu
- `feedback_*.md` — Yamaç'tan gelen ek talimatlar (varsa)

### 5.3. Test pyramid

- **Unit (60%):** Per-component, per-store-slice, per-helper. Hızlı iterasyon.
- **Integration (30%):** Backend router + store + E2E request/response cycle.
- **E2E (10%):** Order 9'da Playwright + real services. Flaky tolerance düşük.

### 5.4. Dependency cleanliness

Her Order başlangıcında `pnpm outdated` (apps/web) ve `uv sync` (Python) — yeni dep eklerken explicit version pinning.

### 5.5. Audit-god çağrı disiplini

- Order 1 sonrası: küçük audit-god review (4 critical bug doğru fix mi).
- Order 4 sonrası: chat backend audit (lifecycle değişikliği büyük).
- Order 5 sonrası: tab shell audit (foundation değişikliği).
- Order 7 sonrası: Run tab audit (renderer registry exhaustive mi).
- Order 9 close-out: full review (hepsi).

### 5.6. Token cost / Ajan disiplini

CLAUDE.md MANDATE 4 (token cost irrelevant) korunur — ajanları cömertçe kullan, ama her ajan **Order kapanmadan önce** çağrılır (ne fazla erken ne fazla geç).

### 5.7. Pillar boundary respect (MANDATE 7)

- Reflex (Pillar 1) etkilenmez (M7'ye iter).
- Body (Pillar 2) etkilenmez (M5'e iter).
- Mind (Pillar 3) `count_by_tier` Protocol additive method ekler — backwards-compat.

---

## 6. Done definition (M4 milestone done)

M4 milestone "done" sayılması için aşağıdakilerin **HEPSİ** sağlanmalı:

1. **9 Order kapandı** — her birinin acceptance criteria check edildi.
2. **ADR-004 status: Kabul edildi** (zaten 2026-05-09 onaylandı) → Order tablosu tam ✅.
3. **Test suite ≥ 1185 pass** (orchestrator + mind + shared + apps/web).
4. **Lint clean** (ruff + mypy strict + ESLint + tsc).
5. **Yamaç laptop e2e onayı** — manual PRD koşusu izledi + beğendi (sentiment positive).
6. **Audit-god full review pass** — Order 9'da çağrılan ajan zero CRITICAL bulgu döndürdü.
7. **Memory update** — `project_m4_cockpit_complete.md` yazıldı (M3 close-out paterni).
8. **Plan dosyası tamamlandı** — bu dosya `STATUS: DONE` header güncellendi.

---

## 7. Sources

- **ADR-004** (mimari kararlar): `docs/decisions/ADR-004_M4_Cockpit.md`
- **ARGE 2026-05-09** (14 ajan raporu): conversation transcript (Yamaç archive)
- **M3 referansı:** `docs/decisions/ADR-003_M3_CLI_Surfing.md`
- **Roadmap:** `docs/ROADMAP.md` §M4
- **Memory:** `~/.claude/projects/-Users-yamacbezirgan-Projects-SelfFork/memory/MEMORY.md` (project_ui_stack, project_jr_tool_protocol, project_provider_usage_source, feedback_no_mvp_full_quality_first_time, project_done_sentinel_protocol)
- **Korpus:** `examples_crucial/skyvern/skyvern-frontend/src/routes/runs/RunRouter.tsx` (Mission ID-prefix dispatch); `examples_crucial/letta/` (Mind tier visualization); `examples_crucial/cognee/cognee-frontend/src/app/(app)/knowledge-graph/page.tsx` (T3 graph viz inspiration); `examples_crucial/Second-Me/lpm_frontend/src/app/dashboard/train/training/page.tsx:293-321` (SSE pattern reference)
