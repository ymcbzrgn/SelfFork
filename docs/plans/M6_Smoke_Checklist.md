# M6 v3 Pivot — Operator Deploy Smoke Checklist

> **Tarih:** 2026-05-17
> **Bağlam:** ADR-006 ACCEPTED — v3 pivot kod tarafı MV %100 done. Bu checklist operator manuel smoke + Telegram + destructive flow validation için.
> **Hedef sıralama:** 1 → 10 sırayla; bir senaryo fail ederse sonraki senaryoya geçilmez, durulur ve rapor edilir.
> **Gate:** Adım 1–7 PASS gerekli; 8–10 deferred sub-task'lar için (M6.5 / Telegram outbound / Warden hook olmadan idle state OK).

---

## 0. Ön-Koşullar

Tüm senaryolardan ÖNCE:

```bash
cd /Users/yamacbezirgan/Projects/SelfFork

# Frontend typecheck
cd apps/web && npx tsc --noEmit && cd ../..

# Python smoke
.venv/bin/python -m pytest packages/body/tests/sandbox/ -x -q
```

İkisi de yeşilse devam.

Server deploy seçeneklerinden BİRİ aktif olmalı:

**A) Native dev** (en hızlı):
```bash
# Terminal 1
selffork ui --host 0.0.0.0 --port 8765 --no-open

# Terminal 2
cd apps/web && pnpm dev   # port 3000
```

**B) Container** (production-shape):
```bash
cd infra/deploy
cp .env.example .env       # MODEL_ENDPOINT ayarla
docker compose up -d --build
docker compose logs -f selffork
```

Tarayıcı → http://localhost:3000 (dev) veya http://localhost:8765 (container).

---

## 1. Sidebar + Topbar v3 doğrulaması

**Hedef:** Sol sidebar 240px, "⊕ SelfFork" logo + 5 nav item + Self Jr footer; topbar Cmd+K + Live indicator + bildirim zili görünür.

**Adım:**
1. Tarayıcıyı `http://localhost:3000` aç.
2. Sidebar'ı görsel doğrula: Dashboard / Workspaces (expandable) / Talk / Connections / Settings + footer "Self Jr · ● Online · gemma-4 @ mac".
3. Topbar'ı görsel doğrula: sol "Dashboard ▼" + arama input "Search… ⌘K" + sağ bildirim zili + Live pulse pill + ServerCog + HelpCircle + tek harf avatar "·".
4. `[` tuşu sidebar collapse — kontrol et (sub-task, opsiyonel).

**PASS kriteri:** Tüm öğeler görünür, Inter font yüklü, layout shift yok.

---

## 2. Dashboard quota gauges + projects grid

**Hedef:** 5 CLI quota gauge (claude/codex/gemini/minimax/glm), Live Loop hero (idle), Recent activity (boş), Workspaces grid + "+ New".

**Adım:**
1. `/` URL.
2. CLI quota strip görünür — 5 kart yatay flex.
3. Hiçbir sağlayıcıya giriş yapılmadığında: 5 kart hepsi "Sign in →" link (dashed border).
4. `/api/usage/providers` curl ile boş array dönerse Dashboard fail etmesin — her kart "Sign in" stub'a düşer.
5. Live Loop kartı: "Self Jr is waiting for a task" (idle empty state). Border-l outline-variant/30.
6. Recent activity: "No activity yet. Self Jr will start logging when a workspace is active." metni.
7. Workspaces grid: `/api/projects` cevabına göre N proje kartı + "+ New workspace" dashed.

**PASS kriteri:** Boş backend ile UI graceful empty state. Console error yok.

---

## 3. Workspace 4-tab IA (Kanban / Live Run / Notes / About)

**Hedef:** Proje açınca header + 4 tab, URL sync `?tab=...`.

**Adım:**
1. Dashboard'da bir proje kartına tıkla → `/workspaces/<slug>` yüklenir.
2. Workspace header görünür: title + status pill + meta ("X/Y tasks · last activity Zm ago") + 4 ghost butona dikkat ([Switch] [Edit] [Pause Self Jr] [Archive]).
3. Tab listesi (4): **Kanban** (default), **Live Run**, **Notes**, **About**.
4. Tab'a tıkla → URL `?tab=live` / `?tab=notes` / `?tab=about` olur (kanban default'ta URL clean).
5. **Kanban tab:** 4 column (Backlog / In Progress / Review / Done), her column header'ında count. Boş ise "empty" italic.
6. **Live Run tab:** İdle banner görünür ("No live session" hero + Terminal ikon + açıklama).
7. **Notes tab:** "Self Jr hasn't written notes for this workspace yet." empty state.
8. **About tab:** Project meta (slug, created, root_path, description) render edilir.

**PASS kriteri:** Tab switching URL'i değiştirir, geri/ileri butonu doğru tab açar, hiçbir tab fail etmez.

---

## 4. Talk page + composer + chips

**Hedef:** `/talk` çalışır, context dropdown projeleri listeler, slash chip'ler textarea'ya ekler.

**Adım:**
1. `/talk` URL.
2. Header: "Talk" + "Speaker: Self Jr · Context: [Auto-detect (...) ▼]".
3. Conversation feed empty state: 3 örnek prompt chip ile hero.
4. Composer açık: textarea + 5 slash chip + send button.
5. Slash chip'e tıkla → textarea'ya prefix eklensin (`/cli `, `/workspace `, vs.).
6. Context dropdown → "All projects" + her workspace listesi + tıklayınca seçim güncellenir.
7. Enter ile send (boşsa disabled, dolu ise textarea boşalır — backend POST henüz `Coming soon`, error toast OK).

**PASS kriteri:** Hiçbir tıklama console error yapmaz. Dropdown sticky değil.

---

## 5. Connections — provider cards + Telegram status

**Hedef:** `/connections` 5 provider + Telegram bridge card. Telegram status real fetch.

**Adım:**
1. `/connections` URL.
2. 5 provider card görünür: claude (amber pill), codex (green), gemini (blue), minimax (purple), glm (red).
3. Hiçbiri sign-in değilse: "Sign in →" primary button. (Sign-in flow M6.6.)
4. Telegram bridge card: `TELEGRAM_BOT_TOKEN` env unset → "Not configured" + "Connect" button + dl içinde "Bot: —", "Webhook: not set", "Soft confirm: 4 hours", "Last activity: never".
5. `TELEGRAM_BOT_TOKEN=test123 selffork ui ...` ile restart → status "Connected" + green dot olmalı.
6. Footer'da: "Soft confirmation (4h, fail-safe NO) replaces autonomy sliders — see ADR-006 §4.5".

**PASS kriteri:** Telegram fetch fail olursa Connections crash etmez, "Not configured" göstermeye devam eder.

---

## 6. Settings — model endpoint + fine-tune + telegram + advanced

**Hedef:** `/settings` 6 accordion (3 expanded + 3 collapsed default).

**Adım:**
1. `/settings` URL.
2. **Model Endpoint** (expanded): URL + protocol radio + model name + auth radio + health row.
3. **Fine-tune** (expanded): dataset radio (auto/manual) + hyperparams grid (Method/rank/alpha/lr/epochs/target) + training endpoint radio + "Current adapter v1.2 · 47 days old" + [▶ Start training] button.
4. **Telegram bridge** (expanded): soft-confirm select + destructive whitelist editor button + per-category override (prod_deploy 4h / social_outbound 1h).
5. **Theme / Workspace defaults / Advanced** collapsed — toggle ile açılıp kapanır.
6. Advanced açılınca 4 toggle: "Show Self Jr raw thinking" / "audit log" / "vision tier" / "session log".

**PASS kriteri:** Tüm form elementleri etkileşimli (state local). [Start training] tıklayınca `POST /api/reflex/train` → `{ status: "queued" }` döner (M7 worker yok ama job kayıtlı).

---

## 7. Destructive whitelist + pending confirmation banner

**Hedef:** Soft-confirm akışı UI tarafı çalışır.

**Adım:**
1. Backend'e elle bir pending entry yaz:
   ```python
   from selffork_body.sandbox.destructive_whitelist import (
       CandidateAction, DestructiveWhitelist
   )
   from selffork_body.sandbox.pending_confirmations import (
       PendingConfirmationStore
   )
   wl = DestructiveWhitelist.load()
   store = PendingConfirmationStore(audit_path=...)
   cat = wl.match(CandidateAction(tool="git", args=("push", "origin", "main")))
   store.request(category=cat, action=..., workspace_slug="my-project")
   ```
2. `/workspaces/my-project` aç.
3. PendingConfirmationBanner görünür: ⚠ ikon + "PROD push pending approval — git push origin main" + countdown "3h Xm left" + [Approve] / [Cancel] / [Details →] butonlar.
4. [Cancel] tıkla → 200 OK + banner ekrandan kaybolur.
5. Yeni entry ekle + [Approve] tıkla → banner kaybolur, status="approved" persisted.

**PASS kriteri:** Approve / Cancel actions backend'e POST atar, response 200, banner reactive.

---

## 8. Telegram outbound (deferred sub-task — M6.6+ wires)

**Hedef:** Real Telegram bot kurulu + soft-confirm Jr → Sr mesaj atar.

**Adım:** M6 close-out aşamasında **deferred**. Sub-task açıldığında:
1. BotFather → token al → `.env` set.
2. Docker compose restart.
3. Destructive action create → Telegram mesajı operatöre düşmeli.
4. Operator "yes" tıklarsa banner approved olmalı.

**SKIP justification:** M6 close-out without this is acceptable per M6_v2_Pivot_Plan.md "Deferred (M6.5+ sub-tasks)".

---

## 9. Server deploy round-trip (container build)

**Hedef:** `infra/deploy/` docker-compose ile ayağa kalkar.

**Adım:**
1. `cd infra/deploy && docker compose build` (8–10 dk ilk seferde).
2. `cp .env.example .env` + `MODEL_ENDPOINT` real değer.
3. `docker compose up -d`.
4. `docker compose logs -f selffork` — orchestrator startup logs yeşil.
5. `curl http://localhost:8765/api/health` → 200.
6. Tarayıcı http://localhost:8765 — Dashboard yüklenir.
7. Volume kontrolü: `docker volume inspect selffork-data` — workspace state persisted.
8. `docker compose down && docker compose up -d` — restart sonrası workspace state survived.

**SKIP justification:** Yalnız native dev kullanılıyorsa atlanabilir; ileride deploy edileceği zaman çalıştırılır.

---

## 10. Memory + ADR close-out

**Hedef:** v3 pivot session-end memory entries yazılı + future-self ADR-006 link'i bulabilir.

**Adım:**
1. `[[v2-pivot-2026-05-17]]` memory yaz: 12-madde özet + ADR-006 link.
2. `[[full-autonomy-soft-confirm-4h]]` memory yaz: destructive whitelist + 4h fail-safe NO kuralı.
3. `[[server-self-host-linux]]` memory yaz: `infra/deploy/` referansı + scenario notları.
4. `[[v2-ui-rebuild-inprogress]]` memory'i **superseded** olarak işaretle.
5. MEMORY.md index'i güncelle (yeni 3 memory + 1 superseded note).

**PASS kriteri:** Yeni session açıldığında `MEMORY.md` ilk satırlardan ADR-006 + M6 plan + smoke checklist bulunabilir.

---

## S1 — Talk Loop (Wave 2 · ADR-007 §4 S1)

**Hedef:** Operatör ↔ Self Jr konuşması uçtan uca — Talk'tan mesaj →
Self Jr cevabı feed'e stream; geçmiş conversation'lar History'de.

**Ön-koşul:** §0 (backend + frontend up). Model endpoint opsiyonel:
`SELFFORK_TALK_MODEL_ENDPOINT` set ise gerçek Self Jr cevabı; değilse
dürüst "model offline / not configured" notice (no-mock — sahte cevap yok).

**Adım:**
1. `/talk` aç — empty state ("Talk to Self Jr" hero + örnek prompt chip'leri).
2. Composer'a mesaj yaz → Enter.
3. Operator mesajı feed'e bubble olur (WS `talk.message` stream).
4. Endpoint varsa Self Jr cevabı feed'e stream olur (self_jr bubble);
   yoksa "No model endpoint…" notice — sahte cevap YOK.
5. "History" → dropdown geçmiş conversation'ı `[selected]` gösterir.
6. "New chat" → empty state'e reset.

**Backend testi:** `pytest packages/orchestrator/tests/talk/ tests/dashboard/test_talk_router.py` → 39 passed.

**PASS kriteri:** Mesaj uçtan uca round-trip; feed WS ile güncellenir;
History + New chat çalışır; backend 39 test + frontend `tsc --noEmit`
temiz; console'da yalnız favicon 404 (bilinen, zararsız).

---

## S2 — Live Run Theater (Wave 2 · ADR-007 §4 S2)

**Hedef:** Workspace "Live Run" theater + Dashboard "Live Loop" hero,
çalışan round-loop'un GERÇEK verisini gösterir — CLI output akar,
düşünce balonu güncellenir, hero LIVE. Screenshot paneli S2 kapsamı
dışı (round-loop↔Body-vision teli ertelendi) → dürüst boş durum.

**Mimari:** Cross-process store-tail. `selffork run` process'i SQLite
theater DB'sine (`~/.selffork/theater/events.db`) event yazar; ayrı
`selffork ui` process'i tail eder (Talk/chat ile aynı desen).

**Ön-koşul:** §0 + round-loop model runtime'ı. `selffork.yaml`
`runtime.backend: mlx-server` → `mlx_vlm.server` (`uv pip install
mlx-vlm`; Gemma 4 E2B 4bit modeli). CLI agent kurulu (opencode /
claude-code / ...). `--project <slug>` zorunlu (orphan run theater'a
düşmez — `NullTheaterProducer`).

**Adım:**
1. `selffork ui --port 8765`; `/api/loop/active` → `null`,
   `/api/workspaces/<slug>/theater/snapshot` → dürüst boş.
2. `selffork run --project <slug> <prd>` başlat.
3. Run sırasında: Dashboard hero `/api/loop/active`'i 5 sn poll'lar →
   LIVE (workspace · cli · turn · duration · last_thought). Workspace >
   Live Run tab'ında CLI output satır satır, düşünce balonu güncellenir.
4. Run bitince: `active_loops` temizlenir → `/api/loop/active` `null`;
   `theater_events` kalıcı (snapshot geçmişi gösterir).

**Doğrulanmış smoke (2026-05-19):** mlx-vlm kuruldu; gerçek `selffork
run --project m4-smoke-test` 2× koşuldu (mlx-server Self Jr + opencode),
exit 0 / COMPLETED. Theater event'leri üretildi (thought + jr-prompt +
opencode stdout/stderr — `apply_patch Success ... hello.txt`); ayrı
`selffork ui` process'i hepsini `/api/.../theater/snapshot` ile servis
etti — cross-process doğrulandı. `/api/loop/active` run sırasında LIVE
yakalandı (duration 0→42 sn, last_thought dolu), bitince `null`.

**Backend testi:** `pytest tests/theater/ tests/dashboard/test_theater_router.py
tests/lifecycle/test_session_theater.py` geçer (64 S2 testi). Tüm
orchestrator suite: 1019 passed (1 fail = ortam: Ollama açık, S2 dışı).
ruff/mypy temiz (`session.py:827` SIM102 pre-existing, S2 dışı).
`tsc --noEmit` temiz.

**PASS kriteri:** Round-loop event'leri cross-process theater'a düşer;
Dashboard hero canlı; screenshot paneli dürüst-boş; backend + tsc temiz;
audit-god 0 kritik bulgu.

---

## Close-out raporu

Tüm 1–7 PASS + 8–10 deferred/skip notlanmış → M6 ACCEPTED. Operator
`git status` + `git log --oneline -5` ile son commit'lere göz atar ve
karar verir: tek bundled commit mi (önerilen), faz başına commit mi
(daha gözle takipli) ait olduğu hale göre.

Sonraki ADR (007) gündemine giren açık iş kalemleri için bkz.
`M6_v2_Pivot_Plan.md` § "Deferred (M6.5+ sub-tasks)".

---

## S3 — Destructive Warden + Telegram Bridge (Wave 2 · ADR-007 §4 S3)

**Hedef:** Destructive eylem soft-confirm uçtan uca (warden hook →
PendingConfirmationStore → Telegram outbound → operator approve via
UI or Telegram inline button → exec devam) **ve** Telegram inbound
köprüsü (Sr → Jr): operator Telegram'a yazar → Talk feed'inde
operator-role mesajı görünür (aktif workspace yoksa drafts banner).

**Ön-koşul (smoke için):**

- §0 (backend + frontend up).
- Destructive whitelist YAML (default: `packages/body/.../destructive_actions.yaml`).
- Telegram smoke: `SELFFORK_TELEGRAM_BOT_TOKEN` env set + `~/.selffork/operators.json`
  içinde operator chat_id ekli.
- Mode env: `SELFFORK_TELEGRAM_MODE=polling` (dev varsayılan) veya
  `webhook` + `SELFFORK_TELEGRAM_WEBHOOK_URL` (deploy).
- Aynı pending JSONL path iki süreçte: `SELFFORK_PENDING_AUDIT_PATH`
  (varsayılan `~/.selffork/pending_confirmations.jsonl`) hem
  `selffork run` hem `selffork ui` tarafından okunur/yazılır.

**Senaryo (a) — Destructive approve flow (UI yolu):**

1. Geçici test whitelist YAML:
   ```yaml
   destructive_actions:
     - id: demo
       description: "demo: rm test-destructive-marker"
       match_any:
         - tool: rm
           args_contains: ["test-destructive-marker"]
       confirm_window_hours: 1
   ```
   `SELFFORK_DESTRUCTIVE_WHITELIST_PATH=/tmp/demo.yaml`.
2. `selffork run --project demo` başlat (Self Jr opencode'a "rm
   test-destructive-marker" benzeri komut talep ettirilecek).
3. Round-loop'ta sandbox.exec çağrılmadan önce warden yakalar →
   `/api/pending-confirmations` listesinde yeni entry görünür.
4. Workspace ekranında `PendingConfirmationBanner` çıkar.
5. "Approve" tıkla → 200 OK + banner kaybolur + audit'te
   `destructive_action_approved` event'i.
6. Round-loop devam eder, exec çalışır.

**Senaryo (b) — Destructive approve flow (Telegram yolu):**

1. Aynı set-up, ama bridge wire'lı (env token + allowlist).
2. Warden yakalayınca operator Telegram chat'ine inline keyboard'lu
   mesaj düşer: workspace · komut · `[✅ Approve][❌ Cancel][⏰ Extend 2h][💬 Ask me]`.
3. "✅ Approve" tıkla → callback işlenir, store flip eder, round-loop
   devam.
4. PASS kriteri: `/api/telegram/activity` outbound listesinde notify
   ve callback inbound kayıtları görünür.

**Senaryo (c) — Sessizlik = iptal (fail-safe NO):**

1. Short window (`confirm_window_hours: 0` → 0 saatlik yapay TTL veya
   per-test seconds-override).
2. Hiçbir aksiyon yapmadan bekle.
3. `expire_loop` arka plan task'ı sweep yapar → entry `expired` olur.
4. Telegram'a "⏰ Window expired" mesajı düşer.
5. Banner ekrandan kaybolur, audit'te `destructive_action_timeout`.

**Senaryo (d) — Telegram inbound (no active workspace) → drafts:**

1. Talk'ta hiç konuşma yokken Telegram'a "merhaba jr" yaz.
2. `/api/telegram/webhook` veya polling alır → MessageHandler işler →
   `last_active_workspace = None` → drafts queue'ya düşer.
3. Talk sayfasında üst banner "📲 1 Telegram message waiting" + Show /
   Dismiss butonları görünür.
4. "Show" → composer'a mesaj basılır + drafts claim edilir.

**Senaryo (e) — Telegram slash commands:**

1. Telegram'dan `/workspace alpha` → Talk store'da `alpha`'ya bağlı
   conversation yaratılır + last_active_workspace = `alpha` olur.
2. Telegram'dan plain text → conversation'a operator-role olarak
   inject + Talk WS event ile UI'a anında düşer.
3. Telegram'dan `/pause` → `~/.selffork/pause.flag` yazılır.
4. Telegram'dan `/extend <id> 4` → seçilen pending entry'nin
   expires_at'i 4 saat uzar.

**Backend testi:**
`pytest packages/orchestrator/tests/ packages/body/tests/` — 1245+ pass
(S3'le 100+ yeni test geldi: destructive_guard, pending_notify_hook,
destructive_notify, expire_loop, drafts, inbound_router, app_factory,
dashboard s3_endpoints).
`ruff check` + `mypy` temiz (S3 dosyalarında pre-existing dışı 0
finding). `tsc --noEmit` temiz.

**PASS kriteri:**

- Senaryo (a) + (b) round-loop'u kesip approve sonra devam eder.
- Senaryo (c)'de 4h (test'te short window) sonunda eylem otomatik
  iptal + Telegram + audit kaydı.
- Senaryo (d) + (e) Talk feed'i + drafts banner'ı doğru güncellenir.
- audit-god 0 kritik bulgu.

**Kapsam dışı (sonraki sprint'lere):**

- CLI router override gerçek mekanizma (S6) — `/cli` komutu şimdilik
  drafts'a düşer + "S6 yolda" notu.
- Settings UI'da destructive whitelist düzenleyici (S4).
- Webhook setup wizard tam akışı (S5'in `setupTelegram` yolu zaten
  endpoint'i yazıyor, prod URL wizard'ı S5'te tamamlanacak).

---

## S-Quota — CodexBar Sidecar Wave 1 (Backend)

**Hedef:** SelfFork snapper'larının yanına `codexbar serve` sidecar'ı
adapter-shim olarak yerleştirmek — `[[codexbar-adoption-2026-05-22]]`.
SelfFork snappers PRIMARY (sub-second tail), CodexBar SECONDARY (40+
provider coverage, Gemini için OTel telemetry off durumunda CodexBar
gerçek quota dönüyor).

**Ön-koşul (smoke için):**

- `codexbar` binary'si PATH'te (dev: `make install-codexbar` veya
  `./infra/deploy/scripts/install-codexbar.sh --prefix ~/.local/bin`).
  Docker image build'inde Dockerfile otomatik vendor eder
  (checksums pinned olduğunda).
- `infra/deploy/codexbar/manifest.toml` v0.27.0 pin'i + sha256'lar
  doluysa (yoksa `refresh-codexbar-checksums.sh v0.27.0` ile doldur).
- Env (default'lar OK; override etmek istersen):
  - `SELFFORK_CODEXBAR_ENABLED=true` (default; binary varsa otomatik)
  - `SELFFORK_CODEXBAR_PORT=8766` (default)
  - `SELFFORK_CODEXBAR_BIN=/path/to/codexbar` (PATH override)
  - `SELFFORK_CODEXBAR_REFRESH_INTERVAL=60` (serve cache TTL)
  - `SELFFORK_CODEXBAR_READINESS_TIMEOUT=8.0` (probe budget)

**Senaryo (a) — Sidecar boot:**

1. `selffork ui --port 8765` başlat.
2. Lifespan log'larında `codexbar_sidecar_started` (port=8766) görmen
   gerek (binary varsa). Binary yoksa `codexbar_sidecar_skipped` +
   "binary not resolved" — dashboard yine de tam çalışır.
3. `curl http://127.0.0.1:8766/health` → 200.

**Senaryo (b) — Gemini fallback (telemetry OFF):**

1. `~/.gemini/telemetry.log` yok (default kurulumda OTel açık değil).
2. `selffork-orchestrator` Python REPL:
   ```python
   from selffork_orchestrator.usage.codexbar_fallback import build_codexbar_fallback_reader
   from selffork_orchestrator.usage.proactive import ProactiveUsageReader
   reader = build_codexbar_fallback_reader(
       primary=ProactiveUsageReader(),
       codexbar_base_url="http://127.0.0.1:8766",
   )
   import asyncio; snap = asyncio.run(reader.read("gemini-cli"))
   print(snap.source if snap else "no data")
   ```
3. Gemini'de OAuth kurulu + CodexBar configured ise:
   `codexbar:openai-web` (veya `codexbar:oauth`) source label ile snapshot.
4. Hiçbir yapılandırma yoksa → `None` (dürüst).

**Senaryo (c) — Source label primary kazanıyor:**

1. SelfFork snapper (`claude_snap.sh`) çalışıyor +
   `~/.selffork/cli-state/claude-code.json` güncel.
2. Aynı REPL ile `await reader.read("claude-code")` → snapshot'ın
   `source` alanı `selffork-snapper` (veya benzeri SelfFork iç-source
   etiketi) olmalı. CodexBar payload'ı vardır ama PRIMARY snapshot
   wins.

**Senaryo (d) — Graceful degradation:**

1. `SELFFORK_CODEXBAR_ENABLED=false` ile dashboard restart.
2. `codexbar_sidecar_skipped` log'unu gör.
3. UsageAggregator + ProactiveUsageReader hâlâ çalışır (SelfFork
   snappers primary). Hiçbir HTTP endpoint kırılmaz.

**Backend testi:**
```bash
.venv/bin/python -m pytest packages/orchestrator/tests/snappers/test_codexbar.py \
    packages/orchestrator/tests/snappers/test_codexbar_server.py \
    packages/orchestrator/tests/usage/test_codexbar_fallback.py -q
```
→ 36 yeni test (14 snapper + 13 sidecar + 9 fallback).
Full suite: **1285 passed**. ruff + mypy + tsc temiz.

**PASS kriteri:**

- Senaryo (a) sidecar boot + health 200.
- Senaryo (b) Gemini için CodexBar fallback kuralı (telemetry off →
  CodexBar primary olur).
- Senaryo (c) primary kuralı (SelfFork snapper var → CodexBar geri
  düşer).
- Senaryo (d) binary yok → dashboard kırılmaz.
- Full backend suite + lint temiz.

**Kapsam dışı (S-Quota Wave 2 — sonraki session):**

- Frontend: Connections sayfasında provider kartlarında "Source:
  selffork-snapper | codexbar | both" mini etiketi.
- Settings → "CodexBar" alt-bölüm (version pin, auto-update
  toggle, last-bump date).
- `.github/workflows/codexbar-watch.yml` — haftalık release watch +
  `refresh-codexbar-checksums.sh` + PR aç.
- Connections card "Last sync from CodexBar" timestamp.
