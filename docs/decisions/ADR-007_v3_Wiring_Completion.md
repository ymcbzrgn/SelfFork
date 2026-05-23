# ADR-007 — SelfFork v3 Wiring Completion (S1–S8)

## Status

- **Status:** Accepted (2026-05-17), revised 2026-05-18 (6→8 sprint).
- **Type:** Implementation roadmap ADR — sequences the work that turns
  ADR-006's v3 MV scaffold into a fully backend-wired product.
- **Builds on:** [`ADR-006_v2_Pivot.md`](./ADR-006_v2_Pivot.md) (the v3
  dominant ADR — 12-madde karar bloğu, 5-screen IA, deployment model).
- **Trigger:** 2026-05-17 frontend↔backend wiring audit + 2026-05-18
  vision-traceability audit (audit-god).
- **Supersedes:** ADR-006 §9 "Deferred (M6.5+ sub-tasks)" — that loose
  list is replaced by the disciplined S1–S8 sprint plan below.

### Revision note (2026-05-18)

İlk taslak 6 sprint (S1–S6) idi. 2026-05-18 vizyon-izlenebilirlik
denetimi (audit-god) 6-sprint planının **2 kilitli ADR-006 kararını**
sprint dışı bıraktığını buldu: (a) CLI router (ADR-006 §4.6 madde 6),
(b) Telegram inbound / Sr→Jr (ADR-006 §4.7.2). Ayrıca eski S6 aşırı
yüklüydü. Düzeltme: **S6 = CLI Router** (yeni), Telegram inbound **S3**'e
katıldı (S3 artık iki yönlü), eski S6 ikiye bölündü → **S7 Workspace
Actions** + **S8 Dashboard Activity + Final Cleanup**. Sonuç: 8 sprint,
ADR-006'nın 12 kilitli kararının tamamı wire kapsamında.

---

## 0. Yönetici Özeti

ADR-006 v3 pivot'u **MV scaffold** yaklaşımıyla uygulandı (M6 Wave 1):
5 ekran çizildi, 12 component yazıldı, 5 orchestrator router kuruldu,
destructive whitelist + deploy iskelesi geldi. Frontend TypeScript-clean,
backend test-clean, 5 ekran tarayıcıda render oluyor.

**Ama** 2026-05-17 wiring audit'i gösterdi ki UI'ın büyük kısmı backend'e
**bağlı değil**: 13 element canlı, 9 element endpoint-var-producer-yok,
**30+ element stub/dead/hardcoded**. Operatör iş akışının kalbi (Talk'tan
Self Jr'a konuşmak) tamamen no-op; Settings sahte canlı veri gösteriyor
(no-mock kuralı ihlali); ~20 buton `onClick`'siz.

Bu, `feedback_backend_first.md` kuralının ("backend-first, minik minik")
tersine düşüldüğü için oldu — ekranlar önce geldi, producer'lar ertelendi.

ADR-007 düzeltmeyi **8 sprint**e böler (S1–S8), her biri **backend-first**
ve **uçtan uca** — bir feature scaffold değil, gerçekten çalışır biçimde
biter, kendi smoke gate'iyle kapanır. Sıra operatör onaylı: S1→S8.

---

## 1. Tetikleyici — 2026-05-17 Wiring Audit

Operatör sordu: *"frontend'deki HER ŞEY tamamen backend'e bağlı mı?"*
audit-god 5 sayfa + 11 component + 5 router'ı `file:line` kanıtıyla taradı.

**Üç sınıf:**
- ✅ **Canlı bağlı** — gerçek endpoint, gerçek veri akıyor.
- 🟡 **Endpoint var, producer yok** — kontrat hazır ama backend hep
  boş/None döner (örn. `/api/loop/active` → `return None`).
- 🔴 **Stub / dead / hardcoded** — hardcoded `[]`, no-op handler, veya
  `onClick`'siz dead button.

**Sonuç:** ✅ 13 · 🟡 9 · 🔴 30+.

---

## 2. Audit Envanteri (Tam Tablo)

### Dashboard
| UI element | Backend durumu | Sınıf |
|---|---|---|
| CLI Quota gauges | `GET /api/usage/providers` — gerçek (UsageAggregator) | ✅ |
| Workspaces grid | `GET /api/projects` — gerçek (ProjectStore) | ✅ |
| Live Loop hero | `GET /api/loop/active` — hep `None` | 🟡 |
| Recent activity | hardcoded `[]`, endpoint yok | 🔴 |
| New workspace kartı | `/talk?intent=...`'a yönlendiriyor, Talk intent okumuyor | 🟡 |

### Workspace
| UI element | Backend durumu | Sınıf |
|---|---|---|
| Header (isim/status/meta) | `GET /api/projects/{slug}` — gerçek | ✅ |
| Kanban board (okuma) | `GET /api/projects/{slug}/kanban` — gerçek | ✅ |
| About tab | `GET /api/projects/{slug}` — gerçek | ✅ |
| Banner approve/cancel handler | `POST .../approve|cancel` — gerçek | ✅ |
| Pending banner (görünürlük) | store hep boş (`request()` caller'ı yok) | 🟡 |
| Live Run Theater | snapshot hep boş, WS sadece heartbeat | 🟡 |
| Header butonları (Switch/Edit/Pause/Archive) | dead — prop geçilmiyor | 🔴 |
| Kanban Add task / Filter / drag | dead — endpoint var, UI çağırmıyor | 🔴 |
| Theater Pause/Switch CLI/Transcript/show raw | dead — prop geçilmiyor | 🔴 |
| Notes tab + Edit/Add section | hardcoded `[]`, dead butonlar | 🔴 |

### Talk
| UI element | Backend durumu | Sınıf |
|---|---|---|
| Context selector (proje listesi) | `GET /api/projects` — gerçek | ✅ |
| Mesaj listesi | hardcoded `[]`, hiç set edilmez | 🔴 |
| Mesaj gönderme (`onSend`) | no-op — sadece textarea temizler, POST yok | 🔴 |
| New chat / History / Attach butonları | dead | 🔴 |

### Connections
| UI element | Backend durumu | Sınıf |
|---|---|---|
| CLI provider satırları | `GET /api/usage/providers` — gerçek | ✅ |
| Telegram bridge durumu | `GET /api/telegram/status` — gerçek (env okur) | ✅ |
| Sign in / Sign out / Test / Browser preview | dead | 🔴 |
| Telegram Connect | dead — `setupTelegram` var, çağrılmıyor | 🔴 |
| Send test / View log / Bot settings | disabled (kasıtlı) | 🟡 |

### Settings
| UI element | Backend durumu | Sınıf |
|---|---|---|
| Model Endpoint formu | tamamen statik `defaultValue` | 🔴 |
| "Online · 187ms" durum kartı | hardcoded sahte gauge | 🔴 |
| Test connection / Save & restart | dead | 🔴 |
| Fine-tune formu | tamamen statik, "8,432 examples" literal | 🔴 |
| "Current adapter v1.2 · 47 days" | hardcoded | 🔴 |
| Start training | dead — `startTraining` var, çağrılmıyor | 🔴 |
| Telegram/whitelist/override | tamamen statik, "7 categories" literal | 🔴 |
| Theme/Workspace defaults/Advanced | placeholder (kasıtlı) | 🟡 |

### Layout
| UI element | Backend durumu | Sınıf |
|---|---|---|
| Sidebar workspace listesi | `GET /api/projects` — gerçek | ✅ |
| Topbar Live/Offline pill | `GET /api/health` 15s poll — gerçek | ✅ |
| Sidebar footer "Self Jr ● Online / gemma-4 @ mac" | hardcoded | 🔴 |
| Topbar bildirim badge | hardcoded `0` | 🔴 |
| Topbar search / status / help / title dropdown | dead | 🔴 |

---

## 3. Wiring Prensipleri

1. **Backend-first** (`feedback_backend_first.md`). Her sprint backend
   producer/endpoint'le başlar; UI wire ondan sonra. Scaffold-önce
   yaklaşımı bu durumu yarattı — tekrarlanmaz.
2. **Her sprint uçtan uca.** "minik minik" — bir feature scaffold değil,
   gerçekten çalışır biçimde biter. Yarım iş bırakılmaz.
3. **No-mock SIKI.** `[[ui-stack]]` ABSOLUTE no-mock kuralı. Settings'teki
   hardcoded sahte değerler ("187ms", "8,432", "v1.2") S4'te tamamen
   silinir. UI veri gösteriyorsa o veri backend'den gelir; yoksa dürüst
   empty state gösterir.
4. **Her sprint kendi smoke gate'iyle kapanır.** `M6_Smoke_Checklist.md`
   genişletilir; gate PASS olmadan sprint "done" sayılmaz.
5. **Dead button yok.** Bir buton ekrandaysa ya bir aksiyon yapar ya da
   görünür biçimde `disabled` + sebep. Yarım-bağlı handler bırakılmaz.
6. **Test her sprint'te.** Backend: happy + failure path testi. Frontend:
   `tsc --noEmit` temiz. E2E: smoke checklist satırı.
7. **Her kilitli karar bir sprint'e düşer.** ADR-006'nın 12 kilitli
   kararının tamamı S1–S8 içinde wire edilir — hiçbiri "deferred"
   bırakılmaz (6-sprint taslağının hatası buydu).

---

## 4. Sprint Planı — S1→S8

> Sıra operatör onaylı (2026-05-17 + 2026-05-18 revizyon): S1→S8, Claude
> yönetir, her sprint sonunda operatöre browser smoke gösterilir.

### S1 — Talk Loop

**Hedef:** Operatör ↔ Self Jr konuşması uçtan uca. SelfFork'un ana
etkileşim yüzeyi; bu olmadan UI bir vitrin.

**Backend:**
- `talk_router.py` yeni — `GET /api/talk/conversations` (list),
  `GET /api/talk/conversations/{id}` (thread), `POST /api/talk/send`
  ({workspace?, text}), `WS /api/talk/{conversation_id}/stream`.
- **Self Jr session resolver** — Talk mesajı hangi Speaker session'a
  gider? Active workspace context → Speaker. Workspace yoksa global.
- Conversation persistence (SQLite). Mevcut `chat_router` +
  `postChatMessage` session-scoped — Talk için reuse mı, ayrı `/api/talk`
  store mı: S1 ilk kararı. (Öneri: ayrı `/api/talk` — Talk operatör↔Jr,
  chat_router CLI-session-scoped; semantik farklı.)
- Speaker invoke — model endpoint'ten cevap (ADR-006 §4.3 hibrit endpoint).

**Frontend:**
- `app/talk/page.tsx` — `messages` real fetch, `onSend` real POST,
  WS ile streaming cevap, History drawer wire, New chat wire.
- `ChatMessage` component (DESIGN.md §6.3 spec — operator/jr bubble).
- `intent=new-workspace` query param handle (Dashboard "+ New" buradan).

**Smoke gate:** Talk'tan mesaj yaz → Self Jr cevabı feed'e stream olur.
History'de geçmiş conversation görünür.

**Bağımlılık:** Model endpoint reachable olmalı (S4'ten önce manuel
config OK — env/yaml ile set edilir).

### S2 — Live Run Theater

**Hedef:** 3-pane theater + Dashboard Live Loop hero canlı veri gösterir.
Operatörün "film izler gibi" izleme talebi (ADR-006 §5.1.1 adım 3).

**Backend:**
- **Theater event producer** — üç kaynak `theater_router` event bus'a
  push eder: snapper stdout → `cli.output.append`; Body vision
  screenshot → `screenshot.new`; Speaker `<thought_summary>` parse →
  `thought.new`.
- `theater_router.py` — WS'i `asyncio.Event().wait()` yerine event
  bus'tan besle; `_empty_snapshot()` yerine gerçek workspace state.
- `/api/loop/active` — `return None` yerine tmux session registry'den
  derive: active workspace, cli, turn, duration, last_thought.

**Frontend:**
- Zaten wire'lı (`snapshotToState` + WS handler). Producer event
  tiplerini handle et: `cli.output.append` → output append,
  `screenshot.new` → timeline'a ekle, `thought.new` → bubble'a ekle.
- Dashboard `LiveLoopStatus` — `getActiveLoop()` gerçek veri döner.

**Smoke gate:** Bir CLI session başlat → Live Run tab'da terminal output
akar, screenshot timeline dolar, thought bubble güncellenir; Dashboard
hero "LIVE · workspace · cli · turn" gösterir.

**Bağımlılık:** S1 yardımcı (Talk'tan session başlatma) ama zorunlu değil.

### S3 — Destructive Warden + Telegram Bridge (iki yönlü)

**Hedef:** Soft-confirm uçtan uca + Telegram köprüsünün **her iki yönü**.
ADR-006 §4.5 (warden) + §4.7 (Telegram Jr→Sr **ve** Sr→Jr).

**Backend — warden + outbound:**
- **Body warden hook** — CLI subprocess action interception path'ine
  `DestructiveWhitelist.match(CandidateAction)` ekle. Match varsa:
  `PendingConfirmationStore.request()` + action'ı **blokla**.
- **Telegram outbound** — `PtbTelegramBridge` startup'ta instantiate
  (`TELEGRAM_BOT_TOKEN` set ise). Warden hook + ihtiyaç bildirimi
  (ADR-006 §4.7.1 "Supabase auth gerekiyor" tarzı) `bridge.notify()`
  çağırır.
- Approve callback → blocked action devam. Expire (4h) → iptal, audit'e
  `destructive_action_timeout`.

**Backend — Telegram inbound (Sr→Jr):**
- `/api/telegram/webhook` POST handler — gelen mesajı `TelegramInbox`'a
  yazar, sonra route eder.
- **Inbound router** — Sr mesajı → active workspace'in Self Jr Talk
  kanalına inject; aktif workspace yoksa `drafts` queue'ya.
- Telegram slash komutları — `/cli <name>` (router override),
  `/workspace <slug>` (context switch), `/pause`, onay callback'leri.

**Frontend:**
- Pending banner zaten wire'lı. Topbar `pendingCount` badge — hardcoded
  `0` yerine `listPendingConfirmations()` count.
- Connections Telegram kartı — inbound/outbound son aktivite gösterir.

**Smoke gate:** (a) Destructive eylem tetikle → Telegram mesajı düşer +
banner görünür → "approve" → eylem devam. (b) Telegram'dan operatör
mesaj yazar → Talk feed'e Self Jr context'inde düşer.

**Bağımlılık:** Telegram bot token (operatör BotFather'dan alır).
S1 (Talk kanalı inbound hedefi) yardımcı.

### S4 — Settings Persistence

**Hedef:** Ayarlar gerçekten kaydedilir; Settings'teki tüm sahte canlı
veri silinir (no-mock ihlali kapatılır).

**Backend:**
- `/api/settings/model-endpoint` GET/PUT — endpoint URL/protocol/auth.
- `/api/settings/destructive-whitelist` GET/PUT — YAML editor backing.
- `/api/reflex/adapter` — placeholder yerine gerçek manifest reader
  veya dürüst "no adapter trained yet" state.
- Model endpoint health check — gerçek ping.

**Frontend:**
- Model Endpoint formu — fetch + state + submit. "Save & restart" →
  `PUT`. "Test connection" → gerçek health ping.
- Fine-tune formu — state + `startTraining()` wire. "Start training" →
  `POST /api/reflex/train`. **NOT:** gerçek eğitim worker'ı M7 — bu
  sprint trigger'ı kontrata bağlar; smoke gate fine-tune'un queued
  job kaydını test eder, eğitim tamamlanmasını DEĞİL.
- Adapter satırı — `getReflexAdapterInfo()` fetch.
- **Sahte literal'ları sil:** "Online · 187ms", "8,432 examples",
  "v1.2 · 47 days old", "7 categories enabled" → gerçek fetch veya
  dürüst empty state.

**Smoke gate:** Model endpoint URL değiştir → kaydet → orchestrator
restart sonrası kalır. Hiçbir Settings ekranında hardcoded sahte sayı
kalmaz.

**Bağımlılık:** Yok — bağımsız sprint.

### S5 — Connections Actions

**Hedef:** Provider sign-in + Telegram setup çalışır.

**Backend:**
- Provider sign-in flow — Body M5 driver browser-auth. `provider_router`
  mevcut; `POST /api/providers/{name}/signin/start` + `WS .../auth-stream`
  (headless browser canvas mirror).
- Telegram setup — `setupTelegram` endpoint'e bağlı; webhook register +
  persist (`~/.selffork/telegram.yaml`).
- Sign-out, test-connection endpoint'leri.

**Frontend:**
- "Sign in" → modal + Body driver headless browser canvas stream.
- "Connect" (Telegram) → bot token + webhook modal → `setupTelegram()`.
- "Sign out" / "Test connection" / "Browser preview" wire.

**Smoke gate:** Bir provider'a (örn. Claude) sign-in → headless browser
OAuth → cookies persist → status 🟢. Telegram Connect → bot bağlı.

**Bağımlılık:** Body M5 driver (mevcut, ADR-005). S3 (Telegram webhook).

### S6 — CLI Router

**Hedef:** Self Jr'ın "hangi CLI'yi kullanayım" kararı — ADR-006 §4.6'nın
kilitli kararı. **Rotasyon DEĞİL:** task-aware + quota-aware + RAG +
operatör override.

**Backend:**
- `select_cli(workspace, task, candidates)` algoritması (ADR-006 §4.6):
  1. Operatör anlık override (en güçlü — sticky veya tek-turn).
  2. Quota kalan — eşik altı (varsayılan <%10) CLI elenir.
  3. RAG geçmiş performans — `(workspace_slug, task_type, cli) →
     success_rate` affinity store; en yüksek skoru seç.
- RAG affinity store — Mind pillar'a yeni schema; her session sonunda
  `(turn-to-task-complete)` metriği yazılır.
- Quota threshold geçişi — aktif CLI kotası eşiğin altına düşünce router
  otomatik diğer adaya geçer, `cli.switch` event'i (theater'a düşer).
- Operatör override API — `POST /api/router/override` ({workspace, cli,
  sticky}). Talk `/cli` chip + Telegram `/cli` komutu buraya bağlanır.

**Frontend:**
- Workspace theater "Switch CLI" dropdown → `POST /api/router/override`.
- Talk `/cli <name>` slash chip → aynı endpoint.
- (Telegram `/cli` komutu S3'te bağlandı — buraya router endpoint'i.)

**Smoke gate:** Bir workspace'te aktif CLI'nin kotasını eşik altına
düşür → router otomatik diğer CLI'ye geçer, theater `cli.switch`
gösterir. Operatör Talk'tan `/cli gemini` → router itaat eder.

**Bağımlılık:** S2 (theater `cli.switch` event'i gösterir). RAG affinity
için Mind pillar — yoksa S6 quota+override ile başlar, RAG skoru sonra.

### S7 — Workspace Actions

**Hedef:** Workspace ekranındaki tüm dead button + Notes backend'i.

**Backend:**
- `/api/workspaces/{slug}/notes` GET/PUT — Self Jr proje notları
  persistence (Mind pillar notes collection backing).
- Kanban mutation endpoint'leri zaten var (`addKanbanCard`,
  `moveKanbanCard`) — UI'a bağlanacak.

**Frontend:**
- Kanban: Add task (`addKanbanCard`), drag-drop (`moveKanbanCard`,
  @dnd-kit), Filter chip'leri.
- Notes tab — `getNotes`/`putNotes` wire, markdown editor, auto-save.
- Notes Edit / Add section butonları.
- Workspace header: Switch (workspace dropdown) / Edit / Pause Self Jr
  (session SIGTERM) / Archive — handler'lar.
- Theater controls: Pause / Switch CLI (S6 router override'a bağlı) /
  Open transcript / show raw thinking toggle.

**Smoke gate:** Workspace'te hiçbir dead button kalmaz; kanban'a kart
ekle/taşı çalışır, Notes kaydedilir, header/theater butonları aksiyon
yapar.

**Bağımlılık:** S2 (theater), S6 (Switch CLI router override).

### S-Auto — Self Jr Heartbeat (ADR-008 §3-§5)

**Hedef:** Mevcut round-loop'un (iç döngü) üstüne **dış döngü**
(Heartbeat) ekle: ADR-008'in tam implementasyonu. perceive → decide →
act → record nabzı, 8 closed-set eylem, deterministik filter + model
seçer hibrit kontrol-loop. Operatör onayında §11 8 sorunun hepsi
çözüldü (§14 #5 "tek geniş sprint", §11 #4 "spark_only" pre-M7 default).

**Bağımlılık:** S2 (theater), S3 (warden + Telegram outbound), S-Quota
W1+W2 (proactive_source quota signal — Heartbeat'in kota geçidi).

**Tamamlandı (8 Faz tek sprint, 2026-05-23):**

* **Faz A — Scheduler**: `heartbeat/scheduler.py` + `config.py`.
  HeartbeatScheduler StrEnum lifecycle + event queue + reconciliation
  timer + pause/active-hours gate + 6 env switch.
* **Faz B — Legal-action filter**: `actions.py` (8 LegalAction enum) +
  `filter.py` (WorldState + LegalActionFilter 5 deterministik kural).
  ADR-008 §7 Lock #3 — model only selects from this filter's frozenset.
* **Faz C — Deliberation**: `deliberation.py` (ActionDecision +
  DeliberationLayer + Speaker Protocol reuse). Orient→Check→Decide
  prompt + JSON parse + fail-safe WAIT fallback.
* **Faz D — Eylem sözlüğü**: `executor.py` (8 ActionExecutor handler +
  callable injection). Lock #4 — destructive guard subprocess path'inde
  hâlâ tetikleniyor (bypass yok).
* **Faz E — Audit + checkpoint + AIR**: `audit.py` (AuditEntry JSONL) +
  `checkpoint.py` (atomic temp/rename) + `air.py` (panic-keyword +
  sustained-failure detector + critical Telegram alert + cooperative
  self-stop). Researcher gap (arXiv 2602.11749 AIR) kapatıldı.
* **Faz F — Creative mode**: `creative.py` (IdeaSize + CreativeScopeGate
  3-tier B*C mix + IdeationManager Lab workspace persistence). Pre-M7
  default `spark_only` (operator §11 #4).
* **Faz G — Settings panel**: `autonomy.py` (4 preset + YAML store +
  apply_preset) + `dashboard/heartbeat_router.py` (GET/PUT autonomy +
  GET state + POST preset) + `apps/web/app/settings/page.tsx` Autonomy
  accordion (read-only; edit lands in S4).
* **Faz H — Smoke + audit-god + memory + commit-ready**: bu satır +
  M6_Smoke_Checklist.md S-Auto bölümü + project memory entry.

**Smoke gate:** `M6_Smoke_Checklist.md` § S-Auto (Senaryo a-h hepsi
PASS). Backend: 1497 test (önceki 1286 + 211 yeni heartbeat). Frontend
tsc clean. Audit-god 0 CRITICAL.

**S-Auto sonrası deferred:**

* Dashboard Faz H wire — `app.state.heartbeat` daemon'a Telegram
  bridge + task_starter + kanban_card_creator inject (Faz D handler
  `skipped` yerine `executed` olur). S4 ile birlikte tamamlanır.
* Autonomy Settings UI **edit** (preset switcher + knob inputs) — S4
  (Settings Persistence).
* Heartbeat hot-reload — PUT /autonomy şu an restart gerektiriyor.
* S6 CLI router RAG affinity — `cli_seç` action gerçek implementasyon.
* Audit log rotation / size cap.
* M7 dataset SSOT pipeline — Heartbeat audit.jsonl → eğitim verisi.

### S-Memory — Dual-Pool Memory Scoping (ADR-009 implement)

**Hedef:** Operatör 2026-05-23 direktifi (verbatim): *"hivemind sadece
örnekti başka açık kaynakları da araştırıcaz sonra ve en iyi proje
bazlı ve ayrıca ortak genel memory havuzunu yaratıcaz!"* → iki ortogonal
memory pool:

* **PROJECT pool** — `~/.selffork/projects/<slug>/mind/` — proje bazlı
  facts, decisions, kanban events, codebase patterns.
* **GLOBAL pool** — `~/.selffork/global/mind/` — operator identity,
  cross-project refleks, T5 Reflection lessons, dream consolidation.

ADR-002 (6-tier cognitive memory) **immutable** kalır; ADR-009
augment olarak yazıldı (`group_id` primitive + T-pool mapping + Auto
Dream trigger).

**Faz şeması (Faz A → Faz H tek sprint):**

| Faz | Modül | Test |
|-----|-------|------|
| A — Envanter + 5+ kaynak paralel araştırma | explorer-god + 5 selffork-researcher | rapor |
| B — Karar + ADR-009 | 4 MAJOR Q operatör onayı → ADR-009 yazıldı | dokümante |
| C — Storage layer (dual-pool + LanceDB) | `store/base.py` PoolScope · `store/lance.py` (yeni) · `store/pool.py` (yeni) · `pyproject.toml` lancedb core dep · DuckDB DDL group_id migration | 53 yeni test |
| D — T1 Working + T2 Episodic + Heartbeat ingest | `ingest/heartbeat.py` (yeni) · audit.jsonl → T2 ingest pipeline · idempotency_key dedup · tail-follow | 29 yeni test |
| E — T4 Procedural PROJECT/GLOBAL split | `procedural.py` target_group_id parametresi · operator refleks distillation GLOBAL'a | 5 yeni test |
| F — T3 Semantic Graph dual-pool | `graph/base.py` GraphTriple.group_id · `store/pool.py` add_triple/list_triples · per-pool InMemoryGraphStore | 12 yeni test |
| G — T5 Reflection + Auto Dream 4-phase | `reflection/auto_dream.py` (yeni) · 4-condition gate · checkpoint persistence · force_run + maybe_run | 25 yeni test |
| H — Smoke + audit + memory + commit-ready | M6_Smoke_Checklist § S-Memory · ADR-007 §4 patch · audit-god · operator commit | 9 close-out |

**Smoke gate:** `M6_Smoke_Checklist.md` § S-Memory — Senaryo a-h.
Backend ≥1926 test pass + tsc/ruff/mypy clean. LongMemEval
extraction+abstention green; PerLTQA + LoCoMo Faz G+ ileride.

**ADR-009 deliverables (Faz C-G implement):**

1. `PoolScope` primitive — Graphiti `group_id` pattern (`p:<slug>` /
   `g:global`); cross-pool union query.
2. `PoolResolver` (DuckDB + LanceDB + Graph engine pair per pool) —
   lazy init, parallel queries, deterministic merge.
3. Heartbeat audit.jsonl → T2 Episodic ingest pipeline (`ingest/
   heartbeat.py`) — structured-source bypass (Cognee pattern), no LLM.
4. `ProceduralDistiller(target_group_id=...)` — T4 GLOBAL routing.
5. `GraphTriple.group_id` field + per-pool graph store isolation.
6. `AutoDreamRunner` — threshold-gated (24h + 5 sessions + not
   rate-limited + idle) 4-phase pipeline; GLOBAL pool routing.

**S-Memory sonrası deferred (sonraki sprintler):**

* Async two-model graph consolidation LLM path (`graph/consolidation.py`
  → `_llm_path`) — ADR-002 §10 Order 4 ileri.
* MemoryAgentBench Test-Time Learning eval — Order 3 ADR'da
  deferred ama Faz E kapsamına alınmadı.
* PerLTQA + LoCoMo eval suite — Order 5+6 ADR'da.
* Three-pillar bridge (Reflex training schedule) — Order 6, M7 öncesi
  son sprint; S-Memory bridge/exporter scaffold zaten production
  ama Reflex training worker M7 sprint scope.
* Kuzu graph store dual-pool wire (şu an InMemoryGraphStore default;
  KuzuGraphStore opsiyonel extra) — production-scale gerektiğinde.
* Heartbeat dashboard wire (S4 Settings Persistence ile birlikte).
* Plain-md projection GLOBAL pool için (`~/.selffork/global/mind/markdown/`)
  — ADR-009 §8 Faz G+ ileride.

**Bağımlılıklar:**

* ADR-002 — DOMINANT, 6-tier; ADR-009 augment.
* ADR-006 §7 — self-host vision (cloud-bound runtime YASAK).
* ADR-008 — Heartbeat outer loop (audit.jsonl feed kaynağı).
* S-Auto — Heartbeat audit.jsonl yazıyor; S-Memory T2'ye ingest eder.
* S6 CLI Router — RAG affinity Memory T4'e bağlı; S-Memory önce.

**Onay:** Operatör 2026-05-23 4 AskUserQuestion'da hepsinin
"Recommended" seçimini onayladı: (1) group_id + physical separate DB,
(2) Hybrid T-pool split, (3) Heartbeat idle + threshold trigger,
(4) ADR-009 yeni dosya.

### S8 — Dashboard Activity + Final Cleanup

**Hedef:** Son aktivite feed'i + kalan tüm dead button (topbar/sidebar).

**Backend:**
- `/api/activity` aggregate endpoint — audit log + recent sessions
  derive (mevcut `read_session_events` / `list_recent_sessions` reuse).

**Frontend:**
- Dashboard Recent activity — `/api/activity` wire.
- Topbar: Cmd+K command palette wire, system status, help overlay,
  title dropdown.
- Sidebar footer: hardcoded "Online" yerine health + model endpoint
  config'den derive.
- Son dead-button taraması — 5 ekran tam tarama, kalan hiçbir
  `onClick`'siz buton bırakılmaz.

**Smoke gate:** `M6_Smoke_Checklist.md` tüm senaryolar (1–10 + S1–S8 ek
satırları) PASS. 5 ekranda dead button = 0.

**Bağımlılık:** S1–S7 (çoğu temizlik önceki sprint'lerin endpoint'lerine
dayanır).

---

## 5. No-Mock İhlali — Düzeltme Listesi

`[[ui-stack]]` ABSOLUTE no-mock kuralı. Audit şu hardcoded sahte
değerleri buldu (hepsi S4'te silinir):

| Konum | Sahte değer | Düzeltme | Sprint |
|---|---|---|---|
| `settings/page.tsx` Model health | "Online · 187ms · just now" | gerçek health ping | S4 |
| `settings/page.tsx` Fine-tune | "Examples: 8,432" | `/api/reflex` dataset count veya empty | S4 |
| `settings/page.tsx` adapter | "v1.2 · 47 days old" | `getReflexAdapterInfo()` | S4 |
| `settings/page.tsx` whitelist | "7 categories enabled" | `/api/settings/destructive-whitelist` | S4 |
| `sidebar.tsx` footer | "Self Jr ● Online / gemma-4 @ mac" | health + model endpoint config | S8 |
| `topbar.tsx` badge | hardcoded `0` | `listPendingConfirmations()` count | S3 |

**Kural:** Bir UI element veri gösteriyorsa o veri backend'den gelir.
Backend henüz yoksa dürüst empty state gösterir — asla inandırıcı sahte
sayı basmaz.

---

## 6. Milestone Konumu

M6 "v3 Pivot" iki dalga olarak yapılandırıldı:

- **M6 Wave 1 — MV Scaffold (DONE, commit `8d509d5` + `09ad348`):**
  5 ekran, 12 component, 5 router, destructive whitelist + store, deploy
  iskelesi, 6 doc supersession banner. TypeScript-clean, 56 Python test.
- **M6 Wave 2 — Wiring Completion (ADR-007, S1–S8):** her ekran uçtan
  uca backend'e bağlanır. Bu ADR.

M6 Wave 2 kapandığında (8 smoke gate PASS) M6 "ACCEPTED" olur ve M7
(Reflex fine-tune — LAST MILE, ROADMAP) gündeme gelir.

---

## 7. Archive Kararı

ADR-006 ile **tamamen** yer değiştirmiş (partial değil) doküman ve
planlar `docs/archive/superseded/`'a taşındı:

- `ADR-004_M4_Cockpit.md` — 4-tab cockpit IA tamamen ADR-006 §5 ile
  değişti.
- `M4_Cockpit_Plan.md` — M4 milestone M6'ya dönüştü.

**Archive EDİLMEYENLER** (partial superseded — geçerli kısımları var,
banner ile işaretli kalır): ADR-001, ADR-002, ADR-003, ADR-005.
M5 planları — M5 hâlâ canlı pillar, kalır.

---

## 8. Pillar Etkisi

- **Reflex:** S4 fine-tune UI gerçek `/api/reflex/train` + adapter
  manifest. M7 worker'ı bu kontratı dolduracak.
- **Body:** S3 warden hook = destructive interception'ın gerçek entegre
  noktası. S5 provider sign-in = M5 driver'ın UI surface'i. S2 vision
  screenshot → theater producer.
- **Mind:** S1 Talk conversation store + S6 RAG CLI-affinity store +
  S7 Notes collection + S8 activity feed — hepsi Mind'ın session/audit
  verisini surface eder. S2 Speaker thought summary Mind reasoning'iyle
  örtüşür.
- **Orchestrator:** S1 talk_router, S2 theater producer + loop registry,
  S3 telegram inbound router, S6 CLI router, S8 activity endpoint.

---

## 9. Risk ve Trade-off

- **S1 model endpoint bağımlılığı:** Talk gerçek cevap için reachable
  model endpoint ister. S4'ten önce env/yaml ile manuel set edilir;
  smoke test bunu ön-koşul sayar. Operatöre ilk sprint'te sorulur.
- **S2 producer karmaşası:** Üç ayrı kaynak (snapper/vision/speaker) tek
  event bus'a push eder — senkronizasyon dikkat ister. Mitigation: her
  envelope `seq` + `ts` taşır (mevcut WS protokol).
- **S3 fail-safe sessizlik:** Operatör 4h cevap vermezse destructive
  eylem iptal — bazen gerçekten gereken eylem kaçar. ADR-006 §10.1
  mitigation (per-kategori timer, `/extend`) S3'te uygulanır.
- **S6 RAG bağımlılığı:** CLI router'ın RAG affinity skoru Mind pillar'a
  bağlı; Mind hazır değilse S6 quota+override ile başlar, RAG skoru
  sonradan eklenir (graceful degradation).
- **Sprint kayması:** 8 sprint sıralı; S7/S8 önceki sprint'lere bağımlı.
  Bir sprint smoke gate'i fail ederse sonrakine geçilmez (M5 "Bouncing
  Back" disiplini).

---

## 10. Onay

Bu ADR operatör onayıyla kabul edildi:
- **2026-05-17:** Sprint sırası *"Sırayla S1→S6, sen yönet"*; kayıt
  *"docs altına mutlak şekilde yaz... eski ADR'lerden kalma her şeyi
  archive at"*.
- **2026-05-18:** Vizyon-izlenebilirlik denetimi sonrası 6→8 sprint
  revizyonu onaylandı (*"vizyon %100 kapansın"*); ADR-006'ya Operatör
  Günlük Akışı + `@SelfJrBot` düzeltmesi onaylandı.

S1 (Talk Loop) bir sonraki session'da başlar. Handoff prompt'u session
devamlılığını sağlar.

İlgili: [[v2-pivot-2026-05-17]], `ADR-006_v2_Pivot.md`,
`docs/plans/M6_v2_Pivot_Plan.md`, `docs/plans/M6_Smoke_Checklist.md`.
