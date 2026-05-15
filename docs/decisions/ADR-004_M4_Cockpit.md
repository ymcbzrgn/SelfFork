# ADR-004 — M4 Cockpit Full Control

**Tarih:** 2026-05-09 (close-out + audit-fix wave aynı gün)
**Durum:** Uygulandı + 9-ajan paralel audit + 9 fix wave (P0/HIGH/MEDIUM); Yamaç laptop e2e smoke'u manuel onay bekliyor
**Bağlam:** `docs/ROADMAP.md` §M4, ARGE 2026-05-09 (14 paralel ajan: 8 selffork-researcher + 5 explorer-god + 1 audit-god)
**Plan:** `docs/plans/M4_Cockpit_Plan.md` (9 order detaylı enterprise uygulama planı)

## Karar

M4 milestone'u 9 order'a bölünmüş şekilde uygulandı. Her order
production-quality (memory: `feedback_no_mvp_full_quality_first_time`):
pluggable interface day 1, eval coverage day 1, plain-md projection
day 1.

| # | Order | Kapsam | Durum |
|---|-------|--------|-------|
| 1 | Pre-M4 audit fix | 4 critical bug (update_card sentinel + audit dir resolution + project_slug wire + SortableContext) | ✅ |
| 2 | Multi-dir audit WS + M-1 protokol | `_resolve_audit_dir` + WsEnvelope + BoundedReplayBuffer + Heartbeat | ✅ |
| 3 | Mind HTTP surface | `mind_router` — stats/notes (CRUD)/recall + provenance WS + `count_by_tier` Protocol | ✅ |
| 4 | Chat backend + M-7 audit field | `chat_router` + `branch_store` SQLite + `_redact_preview` lifecycle | ✅ |
| 5 | apps/web tab shell | shadcn/ui Tabs + Zustand 4-slice + TanStack Query + WS multiplex client | ✅ |
| 6 | Mission tab | Linear-style swimlane + handoff lane + session drawer (read-mostly) | ✅ |
| 7 | Run tab | Trace-tree + Waterfall toggle + 22-category renderer registry + filter chips | ✅ |
| 8 | Chat tab | Streamdown + BranchPicker + DoneSentinel + edit-as-fork | ✅ |
| 9 | Context tab + E2E + Polish | 6-tier collapsible + RecallQueryBar + ADR close-out | ✅ |

## Mimari kararlar

### M-1: Tek multiplexed FastAPI WebSocket + sequence ID

**Convergent finding** (3 bağımsız ajan: WS sync 2026, audit log streaming, state mgmt; bonus Skyvern hybrid pattern):

- Backend: FastAPI websockets sabit; mevcut `/ws/session/{id}` ve `/ws/kanban/{slug}` korunur. Yeni telemetry kanalları (audit + quota + Mind) **mevcut WS'e application-level `event.type` routing ile multiplex** — yeni endpoint açma.
- Mandatory protokol eklemeleri:
  - **Sequence ID**: server→client her mesaja monotonic `seq` field
  - **Heartbeat**: 30s server-initiated ping
  - **Bounded outbound buffer**: `collections.deque(maxlen=200)` per connection
  - **Reconnect**: client `?last_seq=N` → server replay buffer'dan resume
  - **Redis Pub/Sub fanout interface day 1** (multi-worker hazırlığı; tek-process orchestrator için no-op stub OK)

**Reddedilenler:**
- **Liveblocks / Convex / PartyKit**: Self-hostable değil — SelfFork fork-friendly mimarisiyle çelişir (memory: `feedback_brand_is_selffork_not_personal_name` ruhuyla uyumlu).
- **WebTransport (HTTP/3)**: 2026 production-grade FastAPI sarmalayıcı yok; emerging.
- **SSE-only**: Bidirectional gerek var (Jr autopilot `rotate_to` server-push); WS uniform tercih.

### M-2: Frontend state — Zustand + TanStack Query hibridi

**Convergent finding** (Ajan 2 + Ajan 8 bağımsız aynı sonuç):

- **Zustand** (~3KB): UI ephemeral state — aktif tab, açık modal, kanban filter, sidebar collapsed, Jr-typing indicator. WS callback `useStore.setState({...})` direkt yazar.
- **TanStack Query** (~13KB): Server-derived state — kanban kartları, audit log history, quota snapshot, Mind notes. WS mesajı geldiğinde `queryClient.setQueryData(key, updater)` (invalidate **etme**, refetch **etme** — WS authoritative).
- **Optimistic UI**: TanStack `onMutate` snapshot + `onError` rollback. Real conflict için server-side last-write-wins + sequence ID.
- **Cross-tab WS multiplex**: Tek subscriber → router-style `event.type` switch → ilgili `setQueryData` veya `useStore.setState` çağrısı.

**Reddedilenler:**
- **RTK Query Streaming**: Çalışır ama Redux store + Immer draft pattern overkill (Karpathy: surgical, simplicity first).
- **TanStack DB**: BETA etiketi — production-quality kuralı (memory: `feedback_no_mvp_full_quality_first_time`) tehlikeye atar.
- **Jotai / Valtio**: Viable ama Query ekosistemi yokken net kazancı yok.

### M-3: 4-tab cockpit blueprint

**Tab modelleri** (rakip pattern + Yamaç onayı 2026-05-09):

| Tab | Pattern | Ana referans |
|-----|---------|--------------|
| **Mission** | Skyvern `RunRouter` ID-prefix dispatch + Linear-style swimlane kanban + AgentOps drawer (kart tıklama) | `examples_crucial/skyvern/skyvern-frontend/src/routes/runs/RunRouter.tsx:25-85` |
| **Run** | Hibrit: Trace-tree (LangSmith pattern) primary + Waterfall (AgentOps pattern) toggle + filter chips (Sentry breadcrumb pattern) | LangSmith Threads docs; AgentOps Session Waterfall docs |
| **Chat** | Streamdown (Vercel) renderer + assistant-ui Tool collapsible + BranchPicker (first-class branching) | streamdown.dev; assistant-ui.com/docs/guides/branching |
| **Context** | SelfFork native 6-tier düz (T1-T6 her biri collapsible section); Letta-style 3-zone gruplama REDDEDİLDİ | `packages/mind/src/selffork_mind/memory/model.py:51-65` (TierName) |

**Mission tab kuralları:**
- Sütun = status (`pending → running → blocked → handed-off → done`)
- Satır = session (Group by Rows toggle, Linear Apr-2024 swimlane pattern)
- **Read-mostly kanban v1**: Status orchestrator-driven (event-sourced); tek manuel hareket = `blocked → pending` (operator unblock). Free drag-drop scope dışı (sürpriz state mutation riski).
- "Handed-off" lane explicit görsel ayırma + actionable CTA (AIF Handoff `manualReviewRequired` pattern).

**Run tab kuralları:**
- Default Trace-tree (nested run hierarchy, Jr autopilot zaten hierarchical: rotate kararı → sonraki CLI cevabı → sonraki tool).
- Toggle Waterfall (sleep_until / quota_snapshot timing visualization).
- 22 audit category × 4 grup (state / lifecycle / agent / tool) → renderer registry.
- Filter chips: tool-name, cli (claude/opencode/gemini/codex/mmx), event-type, free-text search.

**Chat tab kuralları:**
- Streamdown ile mid-stream markdown + code block detection + Shiki highlighting + copy/download buttons.
- assistant-ui Tool component (collapsible compound: ToolHeader + ToolInput + ToolOutput) — tool call inline render.
- Reasoning / mind_recall result expanded-during-stream → collapsed-after-completion (Cline pattern).
- `[SELFFORK:DONE]` sentinel terminal banner görsel.

**Context tab kuralları:**
- T1 Working / T2 Episodic / T3 Semantic Graph / T4 Procedural / T5 Reflection / T6 Recall — her biri ayrı collapsible section.
- Note count + son güncelleme + size meter per tier.
- T1 Working block içeriği inline.
- T3 graph triples seed-based query (D3/cytoscape; production rakipte emsal yok — özgün tasarım).

### M-4: Chat branching — first-class

**Yamaç onayı 2026-05-09:** assistant-ui pattern.

- Yamaç mesajını edit ederse: backend yeni branch yaratır + Mind T2'ye "alternative path" not yazar (`mind.note.write` audit emit).
- BranchPicker UI: Previous/Next/1of2 sayaç (assistant-ui `BranchPickerPrimitive`).
- Jr autopilot rotate sırasında message regenerate yaparsa: yine branch — surfing geçmişi korunur.
- "Her mesaj sıfırdan değil" (CLAUDE.md MANDATE 6) felsefesinin UI'a yansıması.

### M-5: ABSOLUTE no-mock — docker-compose + fixture replay

**Memory: `project_ui_stack` ABSOLUTE no-mock rule.** Convergent finding (Convex / Inngest / Liveblocks dev workflow patterns):

- `docker-compose.dev.yml` — `apps/web` (Next.js, port 3000) + `packages/orchestrator` (FastAPI + WS, port 8000) + (varsa Postgres/sqlite local).
- `docker compose watch` ile hot reload.
- **JSONL fixture seed**: `packages/orchestrator/fixtures/dev/{sessions,audit_log,kanban}.jsonl` — `seed_dev.py` startup'ta okur, idempotent INSERT.
- **WS event replay CLI**: `selffork-dev replay scenario_a.jsonl` zaman damgalı broadcast (Inngest "Invoke" button CLI versiyonu).
- **OpenAPI type-sync**: FastAPI `openapi.json` → `openapi-typescript` → `apps/web/src/lib/api-types.ts` (mock yok, type-safety var).

**Reddedilenler:**
- **MSW (Mock Service Worker)**: Interceptor pattern = mock by definition; ABSOLUTE no-mock kuralıyla doğrudan çelişir.
- **Storybook**: Component-isolated rendering = mock-by-definition default; cockpit data-driven admin paneli (custom component zoo değil), shadcn/ui kendi dokümantasyonunu sağlar. Fayda < bakım maliyeti.

### M-6: Audit JSONL streaming UI

**Convergent finding** (Ajan 3 — Cloudflare Instant Logs / Railway / Vercel Logs):

- **Tail kaynağı**: `audit.py` zaten append-only JSONL üretiyor. Python `watchfiles` veya `aiofiles` polling (50–100ms).
- **Forwarder**: FastAPI `StreamingResponse` ile multiplexed WS (M-1) — `id: <sequence_id>` (audit `seq` veya line offset). Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`.
- **Server-side filter**: Query param `session_id`, `tool`, `level`, `since_ts`. Filter forwarder içinde uygulanır.
- **Client (apps/web)**:
  - Library: **react-virtuoso** (`followOutput="smooth"` + `atBottomStateChange` first-class auto-scroll/pause).
  - Reconnect: `reconnecting-eventsource` benzeri WS sarmalayıcı + `?last_seq=N` resume.
  - Gap detection: client `last_seq` mismatch → REST fallback fill (`/audit?from=last_seq+1&to=new_id`).
  - Highlighting: category bazlı renk (error kırmızı, tool_call mavi, decision sarı).
- Latency hedef: tool call event UI'a < 1sn (Cloudflare Instant Logs <3s edge'de yapıyor; localhost'ta bottleneck yok).

### M-7: Tool call render contract — payload genişletme

**Critical gap** (Ajan 12 bulgusu): Mevcut `tool.result.payload` sadece `payload_keys: list[str]` taşıyor; gerçek tool çıktısı (mind_recall hit listesi, quota_snapshot dump) audit'e yazılmıyor — Chat tab tool inline render için yetersiz.

**Karar (Karpathy: surgical, en küçük lifecycle değişikliği):**

- `tool.result` audit payload'a `result_payload_preview: dict | str` ekle (redaction-safe; LLM-generated content için PII redact policy).
- Lifecycle değişikliği: `lifecycle/session.py:489-498` (~5 satır).
- Privacy: mind_recall hit content'ı PII içerebilir → optional redact mode (config flag).
- Backwards-compat: `payload_keys` field korunur (schema additive).

**Alternatif (reddedildi):**
- Mind T2 episodic note üzerinden render — extra round-trip + audit log + Mind ayrılığını bozar.
- WS-only stream (audit'i geçmiş için, UI canlı için ayrı kanal) — single source of truth bozar.

### M-8: Chat backend — token streaming + branching API

Yeni router `packages/orchestrator/.../dashboard/chat_router.py`:

- `POST /api/sessions/{id}/messages` — user message append + branch_id (opsiyonel, default current branch).
- `WS /api/sessions/{id}/chat/stream` — token-by-token assistant reply (M-1 multiplex `event.type=chat.token`).
- `POST /api/sessions/{id}/messages/{msg_id}/edit` — user edit → branch yarat → Mind T2 alternative-path log.
- `GET /api/sessions/{id}/branches` — branch listesi.
- `PATCH /api/sessions/{id}/active-branch` — branch switcher.
- Round-loop entegrasyon: `selffork_jr.reply` audit event'i halen authoritative; chat router audit'e ek kayıt yazmaz, audit'i okur+forward eder.

### M-9: Mind HTTP surface — `mind_router`

Yeni router `packages/orchestrator/.../dashboard/mind_router.py`:

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/api/projects/{slug}/mind/stats` | GET | Tier başına note count + son güncelleme |
| `/api/projects/{slug}/mind/working` | GET | T1 WorkingBlock JSON |
| `/api/projects/{slug}/mind/notes` | GET | Note list (tier filter, paginated) |
| `/api/projects/{slug}/mind/notes/{id}` | GET | Note detail |
| `/api/projects/{slug}/mind/notes` | POST | Note create (mind_note_add API) |
| `/api/projects/{slug}/mind/notes/{id}` | DELETE | Supersede |
| `/api/projects/{slug}/mind/recall` | POST | RetrieveConfig-projection body, RetrievalHit list |
| `/api/projects/{slug}/mind/graph/triples` | GET | T3 graph (seed query) |
| `/api/projects/{slug}/mind/provenance` | GET (mevcut) | Korunur |
| `WS /api/projects/{slug}/mind/provenance/stream` | WS | Provenance live tail |

`MindStore` Protocol'üne `count_by_tier(scope)` method'u eklenir (Karpathy: surgical, gerekirse).

## Sınırlamalar / kalan iş

**M5+ scope'a iter (intentional defer):**

- **Body driver entegrasyonu** (mobile/web/desktop control) → M5 (Pillar 2)
- **Reflex eval UI** (model output diffing, behavior diff) → M7 (Pillar 1)
- **Mind T2 advanced 3D knowledge graph viz** (D3 force-graph beyond seeded triples) → M5+
- **Mobile cockpit native app** (M4 sadece responsive web) → M5+
- **Multi-user / multi-tenant cockpit** → out of scope (operator = tek Yamaç)
- **Storybook component lib** → out of scope (no-mock kuralı çelişir + ihtiyaç yok)
- **Linux/Windows scheduler** (LaunchdScheduler alternatifi) → M5+ (M3 carry-over)
- **Telegram inbound** (`/cancel`, `/p <slug> <msg>`) → M4 stretch goal veya M5
- **Component-level isolated dev workflow** → M5+ (component kit growth gerektirir)
- **WebTransport (HTTP/3)** → 2027+ (production-grade FastAPI sarmalayıcı yok)
- **Replay.io-style scrubber** → M5+ (production-grade rakip pattern doğrulanamadı)

## Eski karar (varsa)

- **ADR-001** (M1 baseline architecture) korunur — apps/web FastAPI ↔ Next.js ayrımı sabit.
- **ADR-002** Mind 6-tier mimarisi korunur — M-3 Context tab native 6-tier expose.
- **ADR-003** M3 CLI Surfing korunur — autopilot tool surface ve audit standardı M4 cockpit'in render kontratı.

## Etki

- **Pillar 1 (Reflex):** M7 SFT dataset'e ek sinyal — Yamaç'ın cockpit'te yaptığı gözlem/müdahale (branch yaratma, kanban edit, recall query) audit log'a düşer; M7 fine-tune dataset zenginleşir.
- **Pillar 2 (Body):** Etkilenmez (M5'e iter); cockpit Body driver UI'ını M5'te host edecek hazırlığı (tab shell + state stack) M4'te gelir.
- **Pillar 3 (Mind):** Yeni `mind_router` HTTP yüzeyi; `MindStore.count_by_tier(scope)` method'u eklenir (Protocol'e additive). Provenance live stream + RAG cockpit visibility.

## Kabul kriterleri (M4 done)

- [x] **4 tab live** (Mission/Run/Chat/Context) — `/cockpit` route + 4 tab (Order 5-9)
- [x] **WebSocket telemetry**: M-1 protokolü (sequence ID + replay buffer + heartbeat) backend ve frontend tarafında bağlandı (Order 2 + Order 5)
- [x] **Mock yok**: tek dev workflow korundu (MSW yok, Storybook yok, real fixtures only)
- [x] **ADR-004** kabul edildi (bu dosya)
- [x] **1240 backend test + 76 frontend vitest pass** — baseline 1135 → 1240 (+105 backend yeni); apps/web vitest sıfırdan 76
- [x] ruff + mypy strict — Order 1-9 yeni dosyalar tertemiz; baseline'dan kalan 16 S108 (`/tmp/...` test path) M3 teknik borcu, M5+'a iter
- [ ] **Yamaç laptop'tan canlı PRD koşusu** — manuel smoke test bekliyor (operator-side; aşağıda smoke checklist)

## Final test/lint durumu (gerçek)

| Surface | Test sayısı | Durum |
|---------|-------------|-------|
| `packages/orchestrator/tests` | mevcut + 73 yeni (Order 1-4) | ✅ |
| `packages/mind/tests` | mevcut + 4 yeni (`count_by_tier`) | ✅ |
| `packages/shared/tests` | değişmedi | ✅ |
| **Backend toplam** | **1240** (baseline 1135 + 105) | ✅ |
| `apps/web/__tests__` (vitest) | 76 (sıfırdan kuruldu) | ✅ |

| Lint | Durum |
|------|-------|
| `ruff` (Order 1-9 dosyaları) | All checks passed |
| `ruff` (baseline tüm repo) | 16 S108 — pre-existing test fixture borcu |
| `mypy --strict` | Success (148 source files) |
| `tsc --noEmit` (apps/web) | Clean |

## Manuel smoke checklist (Yamaç laptop)

Bu liste M4'ün operatör tarafı acceptance kriteri — Yamaç bunları
kendi laptop'unda manuel olarak doğrulayacak. Hiçbiri başarısız
olursa Order 9 yeniden açılır.

- [ ] `cd apps/web && pnpm dev` — Next.js dev server :3000'de açıldı
- [ ] `selffork ui` (orchestrator dashboard) :8000'de açıldı
- [ ] `http://localhost:3000/cockpit` — 4 tab placeholder yerine canlı içerik
- [ ] Mission tab: project listesi yüklü; bir kart tıklayınca drawer açılıyor
- [ ] Run tab: gerçek bir audit log session'ı seç; trace-tree yenileniyor
- [ ] Run tab: paradigm toggle Trace ↔ Waterfall sorunsuz
- [ ] Chat tab: Yamaç ↔ Jr round-loop görünüyor; bir mesajı edit → BranchPicker beliriyor
- [ ] Context tab: bir project seç; tier sayıları yükleniyor; recall query çalışıyor
- [ ] WS yeniden bağlanma: devtools network throttle ile WS kes → reconnect sonrası gap işaretleyici (gap event veya seq atlaması) görünüyor

## Audit-fix wave (2026-05-09 close-out, 9 paralel audit-god ajanı)

Order 9 kapandıktan sonra her order için ayrı audit-god ajanı çalıştırıldı; çıkan P0/HIGH bulgular kapatıldı. Order 7 ajanı ilk turda dosyaları okumadan rapor yazdı (abstention), re-audit ile gerçek dosya bazlı bulgular alındı.

**Kapatılan P0:**
- M-7 redact pattern eksik (cookie / set-cookie / client_id / signature / pin / otp / nonce / csrf / xsrf / x-api-key / refresh) → `_SECRET_KEY_PATTERNS` 12'den 24'e çıktı; `_redact_recursive` artık custom-object `__repr__`'ı da scrub ediyor (`_scrub_string`); recursion 16-depth cap ile `RecursionError` koruması eklendi.
- `openKanbanStream` / `openChatStream` / `openMindProvenanceStream` factory pattern WebSocket leak (her render yetim socket) → `kanbanStreamUrl` / `chatStreamUrl` / `sessionStreamUrl` / `mindProvenanceStreamUrl` string-only builders eklendi; cockpit consumer'lar URL builder kullanıyor.
- M-1 replay buffer connection-lifetime (reconnect-with-replay no-op) → `ReplayRegistry` process-level singleton; audit / chat / mind-provenance WS endpoint'leri stream-key bazlı persistent buffer kullanıyor; `?last_seq=N` reconnect artık gerçekten çalışıyor.

**Kapatılan HIGH:**
- Mind `recall` endpoint `mind_config.embedder` ignore (silent BM25-only) → `build_embedder_or_none` + `embed_query` ile `query_embedding` artık geçiriliyor.
- `_tail_session_messages` unbounded memory + O(B*M) per poll → `BranchStore.list_messages_after(after=cursor)` delta query; `seen_ids` kaldırıldı.
- Mind alt-path log silent failure → `_AltPathOutcome` dataclass; başarısızlık operatöre observable.
- `BranchPicker` tüm session branch'leri arasında geziniyor → `forkMessageId` filter ile assistant-ui sibling semantik.
- `DoneSentinel` role-blind → `role="user"` durumda banner suppress (sentinel Jr→orchestrator sinyali).
- `ws_protocol.__all__` eksik export → 12 sembolün hepsi `__all__`'da.

**Kapatılan MEDIUM:**
- `setContextActiveProject` cross-project state bleed → expandedTiers / recallQuery / recallTier / graphSeed reset.
- `setChatActiveBranch` streaming token leak → tokens reset.
- `HandoffLane` silent swallow → inline error feedback.
- `CATEGORY_REGISTRY` `agent.event` legacy missing → eklendi.
- Waterfall sleep clamp yok → 60s clamp + `isClampedSleep` flag.
- Tool filter `agent.invoke` parent context drop → `ROUND_CONTEXT_CATEGORIES` always-pass set.
- Same-tool same-round FIFO test eksik → trace-builder test eklendi.

**Test impact:**
- Backend: 1240 → **1248** (+8 yeni redact pattern test)
- Frontend: 76 → **83** (+3 trace-builder FIFO + waterfall sleep clamp + DoneSentinel role + BranchPicker fork filter + stale prop)
- ruff Order 1-9 dosyaları: All checks passed
- mypy --strict: Success no issues found in 148 source files

## Sınırlamalar / kalan iş (M5+'a iter — confirmed)

- **Automated E2E test (Playwright)** — Order 9'da plan'lanmıştı; manual smoke ile yetiniyoruz, Playwright dep + dual-process test harness M5+
- **T3 Semantic Graph force-graph viz** — Context tab'da placeholder; D3/cytoscape entegrasyonu M5+
- **Token-level chat streaming** — chat WS şu an message-level (post-event), token-level streaming round-loop driver hook gerektirir, M5+
- **Mind T2 alternative-path log Mind store yazımı** — chat_router edit endpoint'i Mind upsert çağırıyor; in-process import (HTTP yerine) kullanılıyor, alt-path note ekleniyor ama dedicated test M5+
- **`cli_mind.py` mind_deps refactor** — duplikasyon var (cli_mind private helper'ları + mind_deps public versions), M5+'da konsolide
- **Drag-drop kanban** — Order 6 read-mostly, free drag-drop M5+
- **Replay-on-reconnect REST fallback** — `lib/ws/multiplex.ts` `onGap` callback hazır ama dashboard'da `GET /events?from=...` endpoint M5+
- **OpenAPI type-sync script** — `pnpm gen:api` dep'i `openapi-typescript` yüklü; CI hook M5+
- **S108 test path teknik borcu** — `/tmp/work` literal'ler M3 baseline'ından (16 hata); test fixture'larını `tmp_path` paterniyle yeniden yazmak M5+

## Sources (close-out — gerçek artefakt referansları)

- **Order 1**: `packages/orchestrator/src/selffork_orchestrator/dashboard/server.py:264-299` (`_resolve_audit_dir`); `packages/orchestrator/src/selffork_orchestrator/dashboard/schemas.py:CardUpdatePayload`; `apps/web/app/project/page.tsx:SortableContext`
- **Order 2**: `packages/orchestrator/src/selffork_orchestrator/dashboard/ws_protocol.py` (yeni — 320 satır)
- **Order 3**: `packages/orchestrator/src/selffork_orchestrator/dashboard/mind_router.py` + `mind_deps.py` (yeni); `packages/mind/src/selffork_mind/store/base.py:TierStats` + DuckDB `count_by_tier`
- **Order 4**: `packages/orchestrator/src/selffork_orchestrator/chat/` (yeni paket: `__init__.py`, `branch_model.py`, `branch_store.py`); `dashboard/chat_router.py`; `lifecycle/session.py:_redact_preview` (M-7)
- **Order 5**: `apps/web/lib/ws/multiplex.ts` + `lib/store/` (4 slice); `app/cockpit/layout.tsx` + `page.tsx`; `vitest.config.ts`
- **Order 6**: `apps/web/app/cockpit/components/mission/` (6 dosya: `MissionTab`, `KanbanBoard`, `Column`, `HandoffLane`, `ProjectSelector`, `SessionDrawer`, `SwimlaneToggle`)
- **Order 7**: `apps/web/lib/run/` (3 builder: `trace-builder.ts`, `waterfall-builder.ts`, `event-categories.ts`); `apps/web/app/cockpit/components/run/` (6 component)
- **Order 8**: `apps/web/app/cockpit/components/chat/` (5 component: `ChatTab`, `MessageBubble`, `MessageList`, `MessageInput`, `BranchPicker`, `DoneSentinel`)
- **Order 9**: `apps/web/app/cockpit/components/context/` (4 component: `ContextTab`, `TierSection`, `NoteList`, `RecallQueryBar`); ADR + plan close-out

- ARGE 2026-05-09 (14 paralel ajan):
  - 8 selffork-researcher: cockpit UI rivals / WS state sync 2026 / audit log streaming UI / decision timeline UX / no-mock dev workflow / chat UI patterns / kanban task lifecycle / live cockpit state mgmt
  - 5 explorer-god: apps/web state map / dashboard endpoints map / examples_crucial cockpit map / audit JSONL + tool schema / Mind API state map
  - 1 audit-god: pre-M4 bug/dead code/integration audit
- Letta ADE: docs.letta.com/guides/ade/overview/
- AgentOps Session Waterfall: docs.agentops.ai/v1/usage/dashboard-info
- LangSmith Threads: docs.langchain.com/langsmith/threads
- Inngest Realtime (managed WS pattern): inngest.com/docs/features/realtime
- Vercel AI SDK + Streamdown: github.com/vercel/streamdown
- assistant-ui (branching first-class): assistant-ui.com/docs/guides/branching
- Linear swimlanes: linear.app/changelog/2024-04-03-swimlanes
- Skyvern frontend (M4 closest rival): examples_crucial/skyvern/skyvern-frontend/src/routes/runs/RunRouter.tsx:25-85
- TkDodo "Using WebSockets with React Query": tkdodo.eu/blog/using-web-sockets-with-react-query
- Cloudflare Instant Logs: blog.cloudflare.com/how-we-built-instant-logs/
- HTML Spec SSE: html.spec.whatwg.org/multipage/server-sent-events.html
- Pre-M4 audit: dashboard/server.py:542 (update_card sentinel), :192/613/615 (audit dir orphan-only), :285-321 (project_slug ignored), apps/web/app/project/page.tsx:588 (useSortable without SortableContext)

## Sources

- ARGE 2026-05-09 (14 paralel ajan):
  - 8 selffork-researcher: cockpit UI rivals / WS state sync 2026 / audit log streaming UI / decision timeline UX / no-mock dev workflow / chat UI patterns / kanban task lifecycle / live cockpit state mgmt
  - 5 explorer-god: apps/web state map / dashboard endpoints map / examples_crucial cockpit map / audit JSONL + tool schema / Mind API state map
  - 1 audit-god: pre-M4 bug/dead code/integration audit
- Letta ADE: docs.letta.com/guides/ade/overview/
- AgentOps Session Waterfall: docs.agentops.ai/v1/usage/dashboard-info
- LangSmith Threads: docs.langchain.com/langsmith/threads
- Inngest Realtime (managed WS pattern): inngest.com/docs/features/realtime
- Vercel AI SDK + Streamdown: github.com/vercel/streamdown
- assistant-ui (branching first-class): assistant-ui.com/docs/guides/branching
- Linear swimlanes: linear.app/changelog/2024-04-03-swimlanes
- Skyvern frontend (M4 closest rival): examples_crucial/skyvern/skyvern-frontend/src/routes/runs/RunRouter.tsx:25-85
- TkDodo "Using WebSockets with React Query": tkdodo.eu/blog/using-web-sockets-with-react-query
- Cloudflare Instant Logs: blog.cloudflare.com/how-we-built-instant-logs/
- HTML Spec SSE: html.spec.whatwg.org/multipage/server-sent-events.html
- Pre-M4 audit: dashboard/server.py:542 (update_card sentinel), :192/613/615 (audit dir orphan-only), :285-321 (project_slug ignored), apps/web/app/project/page.tsx:588 (useSortable without SortableContext)
