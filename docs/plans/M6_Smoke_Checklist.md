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

- ~~Frontend: Connections sayfasında provider kartlarında "Source:
  selffork-snapper | codexbar | both" mini etiketi.~~ ✅ Wave 2'de tamamlandı
- ~~Settings → "CodexBar" alt-bölüm (read-only status).~~ ✅ Wave 2'de tamamlandı
- ~~`.github/workflows/codexbar-watch.yml` — haftalık release watch +
  `refresh-codexbar-checksums.sh` + PR aç.~~ ✅ Wave 2'de tamamlandı

---

## S-Quota — CodexBar Sidecar Wave 2 (Frontend + Auto-update)

**Hedef:** Wave 1'in opt-in default'unu opt-out'a çevirip Connections
+ Settings UI'a CodexBar source görünürlüğü vermek; haftalık release
watch GitHub Action'ı kurmak.

**Ön-koşul:** Wave 1 commit edilmiş + `~/.codexbar/config.json` varsa
(opt-out default), `infra/deploy/codexbar/manifest.toml` sha256'ları
pinlenmiş (`refresh-codexbar-checksums.sh v0.27.0` çalıştırılmış).

**Senaryo (a) — Opt-out default + auto-detect:**

1. `SELFFORK_CODEXBAR_ENABLED` env unset, `codexbar` PATH'te.
2. `selffork ui --port 8765` boot et.
3. Log'da `codexbar_sidecar_started` görmek gerek (auto-detect).
4. `SELFFORK_CODEXBAR_ENABLED=false` ile restart — `codexbar_sidecar_skipped`.

**Senaryo (b) — Connections card source label:**

1. Mac local: SelfFork claude snapper aktif + `~/.selffork/cli-state/claude-code.json` taze.
2. Connections sayfasını aç. Claude kartında "Source: snapper" mini etiketi görmek gerek.
3. Aynı anda CodexBar çalışıyorsa "Source: snapper+codexbar" olur.
4. Gemini için snapper YOK + CodexBar varsa "Source: codexbar".

**Senaryo (c) — Settings → CodexBar status:**

1. Settings → CodexBar accordion'ı aç.
2. State pill (READY / FAILED / DISABLED), Port, Binary path, Base URL render olmalı.
3. 15 sn poll otomatik refresh — sidecar restart edilirse state değişir.
4. Edit yok (read-only); "Wave 2 view, edit lands in S4" notu görünür.

**Senaryo (d) — codexbar-watch.yml workflow:**

1. GitHub Actions tab → "codexbar-watch" workflow → "Run workflow" manual dispatch.
2. (Optional) version input ile spesifik tag (`v0.28.0`).
3. Workflow `gh api`'den son release tag'ini alır; pin'le aynıysa skip; farklıysa `refresh-codexbar-checksums.sh` çalıştırır.
4. `peter-evans/create-pull-request@v7` ile `codexbar/bump-vX.Y.Z` branch'ında PR açar (reviewer checklist + labels: `codexbar`, `dependencies`, `auto-bump`).

**Backend testi:**
```bash
.venv/bin/python -m pytest packages/orchestrator/tests/ packages/body/tests/ -q
```
→ **1286 passed** (Wave 1 + Wave 2; Wave 2'de net yeni test eklenmedi,
mevcut tests opt-out default'a göre güncellendi).
`ruff` + `mypy` + `tsc` temiz.

**PASS kriteri:**

- Senaryo (a) opt-out default + auto-detect.
- Senaryo (b) Connections source label görünür ve tutarlı.
- Senaryo (c) Settings status panel state pill + meta.
- Senaryo (d) workflow manual dispatch ile çalışır; cron Monday 09:00 UTC.
- Full backend suite + tsc temiz.

**Wave 2 ile çıkan deferred:**

- Auto-update workflow'unun gerçek bir CodexBar release tag'i ile
  smoke gate'i — operatör manual dispatch test'i (workflow ilk
  çalıştığında gerçek tarball indirip checksum verify yapar).
- F-01 PID-reuse race (Wave 1'den taşındı; global subprocess hardening
  pass'inde S-Auto sonrası).
- F-12 connection-pool optimization (Wave 1'den taşındı; ihtiyaç
  görünürse Wave 3'te).
- Settings'te edit + auto-update toggle + binary path override — S4
  (Settings Persistence) sprint'inde.

---

## S-Auto — Self Jr Heartbeat (ADR-008 §3-§5, 8 Faz Tek Sprint)

**Hedef:** Mevcut round-loop'un üstüne **dış döngü** (Heartbeat)
ekleme — *perceive → decide → act → record* nabzı ile "hangi proje /
task / şimdi mi bekle mi" otonom kararı. ADR-008 §7 12 lock onaylı,
§11 8 açık soru çözüldü (operator + researcher synthesis):
* #4 yaratıcı kadran: pre-M7 default `SPARK_ONLY` (sadece-fikir),
  Settings'ten 4 kademe ayarlanabilir.
* #5 sprint yapısı: **tek geniş S-Auto** (executive + creative birlikte).
* #6 isim: `Heartbeat` korundu (enterprise tutarlılık; ADR-008 §13'e
  Letta-deprecate açıklaması eklendi).

**Ön-koşul (smoke için):**

- §0 (backend + frontend up).
- Heartbeat default opt-in (Wave 1 disiplini):
  `SELFFORK_HEARTBEAT_ENABLED=true` env set veya `~/.selffork/heartbeat/
  autonomy.yaml` exists ile `enabled=true`.
- Speaker endpoint (deliberation wire için): `SELFFORK_TALK_MODEL_ENDPOINT`
  + `SELFFORK_TALK_MODEL` set; yoksa daemon tick atar ama decide stage
  yapmaz (Faz B observe-only).
- `~/.selffork/heartbeat/` writable (audit.jsonl + checkpoint.json
  yazımı için).
- Pause flag yolu: `~/.selffork/pause.flag` (S3 `PauseSignal` reuse).

**Senaryo (a) — Daemon boot + observe (Faz A scaffold):**

1. `SELFFORK_HEARTBEAT_ENABLED=true selffork ui --port 8765` başlat.
2. Lifespan log'larında `heartbeat_started` (tick_seconds + active_hours
   + timezone payload'ı) görmek gerek.
3. `curl http://127.0.0.1:8765/api/heartbeat/state` → `state: "running"`,
   `tick_count >= 1` (kısa bekleme sonrası).
4. `SELFFORK_HEARTBEAT_ENABLED` unset → `heartbeat_skipped_disabled`;
   `/api/heartbeat/state` → `state: "disabled"`.

**Senaryo (b) — Pause flag short-circuit (Faz A reaktif gate):**

1. Daemon running.
2. `touch ~/.selffork/pause.flag`.
3. Tick'ler `tick_count` artırmıyor (perceive stage'de short-circuit;
   filter çağrılmıyor → `last_legal_actions` None kalıyor).
4. `rm ~/.selffork/pause.flag` → tick'ler devam ediyor.

**Senaryo (c) — Legal-action filter rules (Faz B):**

1. Daemon running, kanban event'i submit et:
   ```bash
   curl -X POST http://127.0.0.1:8765/api/heartbeat/state  # no-op; rely on internal events
   ```
2. `last_legal_actions` populated; default WorldStateBuilder'da
   `creative_mode_enabled=False` → `fikirleş` set'te değil.
3. Pause aktif → set sadece `{bekle, kendini_durdur}`.
4. Tüm CLI quotas 99% → `task_başlat` ve `cli_seç` set'ten çıkar.

**Senaryo (d) — Deliberation layer (Faz C):**

1. `SELFFORK_TALK_MODEL_ENDPOINT=http://localhost:11434/v1
   SELFFORK_TALK_MODEL=gemma3:2b SELFFORK_HEARTBEAT_ENABLED=true selffork ui`
   başlat.
2. Bir kanban event'i veya reconciliation timer tetikle.
3. `/api/heartbeat/state` → `last_decision.action` (modelin seçtiği
   eylem) + `last_decision.reasoning` (kısa Türkçe gerekçe).
4. Model unhealthy ise `last_decision.fallback=true` + action=WAIT.

**Senaryo (e) — Action executor (Faz D):**

1. Yukarıdaki state'de `last_result.outcome` ∈ {executed, deferred,
   skipped, failed}.
2. WAIT/SELF_STOP → executed (pure).
3. TASK_START/OPERATOR_ASK/KANBAN_SUGGEST → callable wired değilse
   `skipped` (Faz H dashboard wire yapacak).
4. SESSION_RESUME / CLI_SELECT / IDEATE → `deferred` (Faz F'de IDEATE
   `executed` döner).

**Senaryo (f) — Audit + checkpoint + AIR (Faz E):**

1. Daemon tick atınca `~/.selffork/heartbeat/audit.jsonl` dosyasında
   her tick için JSON-line eklendi:
   ```bash
   tail -1 ~/.selffork/heartbeat/audit.jsonl | jq .
   # {tick, timestamp, trigger, world_state, legal_actions,
   #  decision_action, decision_reasoning, result_outcome,
   #  result_metadata, air_alert, idempotency_key}
   ```
2. `~/.selffork/heartbeat/checkpoint.json` her tick refresh oldu
   (`{step, progress, next_action, updated_at}`).
3. AIR test: Speaker'a "I am panicking and covering up the failure"
   gerekçesi döndüren stub bağla → daemon self-stop, `last_air_alert`
   populated (severity=high), emergency Telegram (bridge wired'sa)
   mesajı gönderildi.

**Senaryo (g) — Creative mode (Faz F):**

1. `~/.selffork/heartbeat/autonomy.yaml` yaz:
   ```yaml
   preset: tam
   enabled: true
   creative_dial: spark_only
   ```
2. Daemon restart → builder Settings'ten okur, creative_mode_enabled=True.
3. Idle tick'te IDEATE seçildiğinde `~/.selffork/lab/ideas/<date>-<size>-<id>.md`
   dosyası yazıldı (`spark_only` default Faz F için).
4. Idea text "new project: ..." içeriyorsa size=large; word_count>180 ise large.

**Senaryo (h) — Settings panel (Faz G):**

1. `curl http://127.0.0.1:8765/api/heartbeat/autonomy` → 4 preset
   default (`dengeli` when no YAML).
2. `curl -X POST http://127.0.0.1:8765/api/heartbeat/autonomy/preset/tam`
   → `~/.selffork/heartbeat/autonomy.yaml` yazıldı, response
   `{preset: tam, creative_dial: spark_only, ...}`.
3. `curl -X PUT http://127.0.0.1:8765/api/heartbeat/autonomy
   -d '{"preset":"dengeli","enabled":true,...}'` → persist + return.
4. Settings page'inde Autonomy accordion açık (preset + creative dial +
   tick + reconciliation + concurrency + active hours render); 15 sn
   poll; "edit lands in S4" notu.
5. Daemon restart sonrası YAML değişikliği effect (Faz G hot-reload
   yapmıyor; persist now, effect next boot).

**Backend testi:**
```bash
.venv/bin/python -m pytest packages/orchestrator/tests/heartbeat/ -q
```
→ **211 heartbeat test passed** (Faz A 19 + Faz B 32 + Faz C 22 + Faz D
28 + Faz E 53 + Faz F 26 + Faz G 31).
Full suite:
```bash
.venv/bin/python -m pytest packages/orchestrator/tests/ packages/body/tests/ -q
```
→ **1497 passed** (önceki 1286 + 211 yeni). `ruff` + `mypy` + `tsc` temiz
(13 heartbeat source files 0 mypy hata, ruff All checks passed).

**PASS kriteri:**

- Senaryo (a)-(h) hepsi PASS.
- audit-god rigorous review 0 CRITICAL bulgu.
- Full backend + tsc + ruff + mypy temiz.
- Audit JSONL + checkpoint JSON persist + read-back roundtrip ok.
- AIR panic-detect daemon halt + emergency Telegram alert wired'sa.
- 4 preset POST /api/heartbeat/autonomy/preset/{name} ile YAML yazımı.

**Kapsam dışı (S-Auto sonrası sprintler):**

- Dashboard'un Faz H wire'ları (lifespan'da TelegramBridge / task_starter /
  kanban_card_creator inject) S4'le birlikte tamamlanır.
- Autonomy Settings UI **edit** (preset switcher dropdown + knob inputs)
  S4 (Settings Persistence) sprint'inde.
- Heartbeat hot-reload (PUT /autonomy effect immediately) deferred.
- S6 CLI router gerçek RAG affinity — şu an `cli_seç` deferred.
- Audit log rotation / size cap — long-running production deferred.
- M7 Reflex fine-tune entegrasyonu (Heartbeat audit JSONL → M7 dataset
  SSOT) — ADR-008 §9 madde gereği.
- ADR-007 §4'e S-Auto sprint blok eklenmesi (sprint sonu commit ayrı).
- Sabah raporu (`/api/heartbeat/morning-report`) — Autonomy panel'da
  flag var ama generator deferred.

## S-Memory — Dual-Pool Memory Scoping (ADR-009 implement, 8 Faz Tek Sprint)

**Bağlam:** Operatör 2026-05-23 direktifi (verbatim): *"hivemind sadece
örnekti başka açık kaynakları da araştırıcaz sonra ve en iyi proje
bazlı ve ayrıca ortak genel memory havuzunu yaratıcaz!"*. ADR-002
6-tier locked; ADR-009 dual-pool augment olarak yazıldı; gerek koşul
S6 CLI Router RAG affinity için.

### Ön-Koşullar

1. `git status` clean; S-Auto commit `575ec8c` upstream.
2. ADR-002 + ADR-009 + ADR-006 §7 + ADR-008 §3-§5 okundu.
3. `examples_crucial/` 6+ memory repo: letta, mem0, cognee, graphiti,
   Hivemind, Auto Dream deep-read'leri Faz A'da tamamlandı.
4. Operatör 4 AskUserQuestion'a "Recommended" onayı (Faz B).

### Senaryo a — Storage layer (Faz C)

- [ ] `from selffork_mind.store import PoolResolver, PoolScope,
      LanceDBVectorStore, DuckDBMindStore, GLOBAL_GROUP_ID` import OK.
- [ ] `PoolScope(project_slug="foo")` → `group_ids() == ("p:foo",)`.
- [ ] `PoolScope(project_slug="foo", include_global=True)` → `("p:foo", "g:global")`.
- [ ] `PoolScope(include_global=True)` → `("g:global",)`.
- [ ] DuckDB DDL migration: yeni DB'de `group_id TEXT` column var;
      eski DB'de `ALTER TABLE ADD COLUMN IF NOT EXISTS` idempotent.
- [ ] LanceDB `episodic_vectors` tablo schema = `note_id, group_id,
      project_slug, session_id, tier, vector, content_hash, written_at`.
- [ ] `lancedb>=0.30.0` pyproject.toml core dep.

### Senaryo b — Heartbeat ingest (Faz D)

- [ ] `~/.selffork/heartbeat/audit.jsonl` mevcut entries için
      `HeartbeatIngester.ingest_pending()` → her tick için bir T2
      Episodic Note (content `tick=N | trigger=X | action=Y | outcome=Z`).
- [ ] Idempotency: aynı log re-ingest edildiğinde Note sayısı
      değişmiyor (UUID5 collapse).
- [ ] Checkpoint persistence: `audit.ingest-checkpoint.json` atomic
      temp+rename; restart sonrası resume offset.
- [ ] `world_state.last_active_workspace` PROJECT pool routing;
      `None` → GLOBAL pool routing.
- [ ] AIR alert entries → importance=1.5; default importance=1.0.
- [ ] Malformed line → `skipped_malformed` counter; ingest devam.

### Senaryo c — T4 Procedural dual-pool (Faz E)

- [ ] `ProceduralDistiller(store=resolver._project.notes)` PROJECT
      pool'a yazar; `target_group_id=None` default davranış.
- [ ] `ProceduralDistiller(store=resolver._global.notes,
      target_group_id=GLOBAL_GROUP_ID)` GLOBAL pool'a yazar.
- [ ] Cross-pool retrieval `PoolScope(project_slug=..., include_global=True)`
      her iki pool'un T4 pattern'lerini union eder.
- [ ] Mevcut 13 procedural test pass (regression yok).

### Senaryo d — T3 Semantic Graph dual-pool (Faz F)

- [ ] `GraphTriple.group_id` field default None; `to_payload()` set'liyse
      payload'a girer.
- [ ] `resolver.add_triple(triple, pool="project")` → `group_id="p:<slug>"`
      stamped.
- [ ] `resolver.add_triple(triple, pool="global")` → `group_id="g:global"`
      stamped.
- [ ] `resolver.list_triples(pool_scope=PoolScope(..., include_global=True))`
      paralel sorgu + (subject, predicate, obj, source_passage_id) sırasıyla
      deterministic merge.
- [ ] İki ayrı PROJECT resolver (`alpha` + `beta`) filesystem-isolated graph.

### Senaryo e — Auto Dream pipeline (Faz G)

- [ ] `AutoDreamGate` 4 kondisyon ayrı ayrı bloklar: hours, sessions,
      rate-limited, idle.
- [ ] Hepsi geçerse `should_run=True`, `failed_conditions=()`.
- [ ] `AutoDreamRunner.maybe_run()` gate fail → None.
- [ ] `AutoDreamRunner.force_run()` gate'i bypass eder; reflection
      report döner; checkpoint güncellenir.
- [ ] `sessions_counter` async callback hatası gate'i crash etmez
      (telemetry-only; log warning).
- [ ] `bump_sessions(delta=N)` atomic; negatif değer → 0'a clamp.

### Senaryo f — Full backend gate

- [ ] `.venv/bin/python -m pytest packages/mind/tests/ packages/orchestrator/tests/
      packages/body/tests/ -q` → ≥1926 pass.
- [ ] `.venv/bin/python -m ruff check packages/mind/` → All checks passed.
- [ ] `.venv/bin/python -m mypy packages/mind/src/` → Success, no issues.
- [ ] `cd apps/web && npx tsc --noEmit` → clean (frontend wire S4'te,
      bu sprint frontend dokunmadı).

### Senaryo g — audit-god rigorous review

- [ ] `audit-god` agent dispatch — 1 rapor:
      * ADR-009 §1-§5 lock invariants kod ile teyit.
      * Cross-pool query ordering deterministic.
      * Heartbeat ingest idempotency_key dedup atomic.
      * Auto Dream gate 4 condition tüm fail kombinasyonlarında doğru.
      * GLOBAL pool corruption riski (atomic write, çift teardown,
        race condition) test edildi.
      * `target_group_id` ProceduralDistiller geriye uyumlu (mevcut
        13 test pass).
- [ ] Bulgular MAJOR/MINOR sınıflı; CRITICAL = 0 hedef.

### Senaryo h — Commit-ready

- [ ] Memory entry: `project_s_memory_complete_2026_05_23.md` yazıldı.
- [ ] `MEMORY.md` index güncel.
- [ ] ADR-007 §4 S-Memory blok geniş yazıldı (S-Auto bloğu yanına).
- [ ] ADR-002 header'a "Augmented-by: ADR-009" eklendi.
- [ ] Commit message draft operatöre sunuldu (S-Auto formatında).
- [ ] Operatör onayı sonrası tek commit (MANDATE 1).

### S-Memory sonrası deferred (sonraki sprintler)

- Async two-model graph consolidation LLM path (Order 4 ileri).
- MemoryAgentBench Test-Time Learning + PerLTQA + LoCoMo eval suite.
- Three-pillar bridge (Reflex training schedule) — M7 öncesi son sprint.
- Kuzu graph store dual-pool wire (default InMemoryGraphStore;
  Kuzu opsiyonel `[graph-kuzu]` extra altında).
- Heartbeat dashboard wire (S4 Settings Persistence ile birlikte).
- Plain-md projection GLOBAL pool için (`~/.selffork/global/mind/markdown/`).
- ADR-009 §8 AGENTS.md BEGIN/END idempotent insertion (Hivemind H3
  lift; sprint sonu küçük iş).
- `selffork mind dream` CLI komutu (Auto Dream force_run wrapper).
- S6 CLI Router RAG affinity — T4 Procedural query API'sini
  consume edecek; ayrı sprint.

## S4 — Settings Persistence (ADR-007 §4)

**Hedef:** Settings sayfasındaki tüm sahte canlı veriyi yok et;
gerçek persistence ile her form/buton arka uca bağlanır. No-mock
S4-S8 kuralı sertleştirildi: dead UI ya wire'lanır ya silinir.

**Backend (yeni):**

- `GET/PUT /api/settings/model-endpoint` (URL/protocol/model/auth).
- `POST /api/settings/model-endpoint/test` (gerçek health ping).
- `GET/PUT /api/settings/destructive-whitelist` (operatör override —
  YAML full editor).
- `PUT /api/settings/destructive-whitelist/{id}/window` (per-category
  soft-confirm window).
- `GET/PUT /api/settings/codexbar` (version pin / auto_update /
  binary path override).
- `/api/reflex/adapter` honest empty state (manifest reader).
- `/api/reflex/train` fake `estimated_seconds=5h 18m` SİLİNDİ.

**Frontend (`apps/web/app/settings/page.tsx` rewrite):**

- Model Endpoint accordion: controlled inputs + Save + Test connection.
- Fine-tune accordion: hyperparams form + Start training queue.
- Telegram bridge accordion: destructive whitelist full editor + per-
  category window dropdown.
- CodexBar accordion: read-only status + writable knobs.
- Autonomy accordion: preset switcher + creative dial + 8 knob inputs.
- SİLİNDİ: Theme section, Workspace defaults section, Advanced
  toggles section (no-consumer mock).
- "Power user / Vision adapter → `/cockpit/settings/vision`" link kaldı.

**S-Auto F-AG #3 callable inject (S4'le birlikte tamamlandı):**

- `server.py` lifespan'da `HeartbeatScheduler`'a `telegram_bridge`
  (NullBridge → None) + `task_starter` + `kanban_card_creator`
  wire'lı.
- `build_default_heartbeat()` 3 yeni kwarg kabul ediyor.
- Boot log: `heartbeat_callables_wired{telegram, task, kanban}`.

### Senaryo a — Model Endpoint persistence + restart

1. `selffork ui --port 8765` başlat (`SELFFORK_HEARTBEAT_ENABLED=false`
   opsiyonel; daemon kapalıyken de UI tam çalışır).
2. UI Settings → Model Endpoint accordion'unu aç. URL alanını
   `http://10.0.0.42:8080` yap. Protocol `mlx`, Model name
   `gemma-4-26b-a4b-it-4bit`, Auth `api-key` + secret `sk-test`.
3. **Save** → 200 + "Saved ✓" görünür.
4. `cat ~/.selffork/settings/model-endpoint.yaml` → YAML payload
   beklenen değerlerle.
5. UI'yı kapat, orchestrator'ı restart et, UI'yı tekrar aç → form
   aynı değerlerle yüklenmiş olmalı (round-trip).

### Senaryo b — Model Endpoint health probe

1. `Test connection` → endpoint kapalıyken `Unreachable · NNNms ·
   ConnectError` pill'i görünür (sahte "Online · 187ms" yok).
2. `python -m http.server 8080` ile localhost'ta dummy server kaldır,
   yeniden test → `Online · NNNms · status=...` pill'i.

### Senaryo c — Destructive whitelist editor + per-category window

1. Telegram bridge accordion'u aç → "X categories enabled (default)"
   listesi 7 madde (bundled).
2. "Open editor →" tıkla → raw YAML textarea açılır.
3. `prod_deploy` kategorisinin `confirm_window_hours: 4` → `12` yap,
   `Save whitelist` → response `source: override`.
4. `cat ~/.selffork/settings/destructive-whitelist.yaml` → dosya
   yazıldı.
5. Per-category dropdown: `social_outbound`'un 1 saatini 8 saate çek
   → backend `PUT .../social_outbound/window`. `~/.selffork/settings/
   destructive-whitelist.yaml` `social_outbound` window = 8.
6. Orchestrator restart → warden `_load_destructive_whitelist()` aynı
   override path'ten okur (dashboard ve warden senkron).

### Senaryo d — Reflex adapter honest empty state

1. `rm -rf ~/.selffork/reflex/` (M7 öncesi henüz adapter yok).
2. Fine-tune accordion: "Current adapter: No adapter trained yet.
   Reflex fine-tune worker lands in M7..." — sahte `v1.2 · 47 days
   old` YOK.
3. Manuel manifest yaz: `mkdir -p ~/.selffork/reflex/adapters/current
   && echo '{"version":"v0.1","examples":5000,"method":"QLoRA",
   "trained_at":"2026-05-23T12:00:00Z"}' >
   ~/.selffork/reflex/adapters/current/manifest.json`. Sayfayı
   yenile → gerçek `v0.1 · 0 days old · QLoRA · 5000 examples`.

### Senaryo e — Fine-tune queue contract

1. Start training (auto dataset) → 202 + UI'da "Queued · job <id>
   (M7 worker pending)".
2. `curl /api/reflex/training-status/<id>` → `status: queued`,
   `estimated_seconds: null` (sahte 5h 18m YOK).
3. `log_tail` "Real training worker lands in M7" satırını içerir.

### Senaryo f — Autonomy preset + knob edit

1. Autonomy accordion'da `tam` butonuna tıkla → preset değişir,
   `creative_dial` `spark_only` (pre-M7 ceiling).
2. `tick_seconds`'i 1.5'e çek → "Save knobs".
3. `cat ~/.selffork/heartbeat/autonomy.yaml` → `tick_seconds: 1.5`,
   `preset: tam`, `creative_dial: spark_only`.
4. Orchestrator restart → `/api/heartbeat/autonomy` aynı değerlerle
   geri döner.
5. "Save & restart" sonrası daemon kapalı/açık knob'larında değişiklik
   uygulanır (effect-on-restart notu UI'da).

### Senaryo g — CodexBar settings

1. CodexBar accordion'a Version pin `v0.27.0`, Binary path override
   `/usr/local/bin/codexbar`, Auto-update toggle kapalı.
2. Save → `cat ~/.selffork/settings/codexbar.yaml` payload.
3. Restart sonrası dashboard'da değerler aynı; CodexBar status
   "ready/inactive" canlı poll'lanmaya devam.

### Senaryo h — F-AG #3 callable wire (dashboard boot log)

1. `selffork ui` başlat. Log'larda `heartbeat_callables_wired
   telegram_wired=<bool> task_starter_wired=true
   kanban_creator_wired=true` satırı görmek gerek.
2. Telegram bot token configure edilmediyse `telegram_wired=false`
   ama task + kanban wire'lı.
3. `SELFFORK_HEARTBEAT_ENABLED=true` + Self Jr Talk endpoint env
   konfigüre edilmişse daemon `OPERATOR_ASK` action seçtiğinde
   gerçek Telegram mesajı düşmeli (operatör chat'inde); `TASK_START`
   seçtiğinde `~/.selffork/projects/<slug>/heartbeat-prds/<ts>.md`
   PRD dosyası + spawn'lanan selffork run subprocess pid'i audit
   JSONL'inde görünür; `KANBAN_SUGGEST` seçtiğinde aktif project'in
   Kanban board'unda yeni card belirir.

### Senaryo i — No-mock kuralı tam sweep

1. Settings page'inde sahte literal taraması:
   `grep -E '187ms|8,432|v1.2 ·|47 days|7 categories|coming soon|
   Wire-in pending|Self Jr raw thinking' apps/web/app/settings/
   page.tsx` → sıfır eşleşme.
2. 3 dead section silindi: `grep -n 'theme\|workspace\|advanced'
   apps/web/app/settings/page.tsx` → sadece dosya yorumlarında
   referans varsa OK; Section type union'da yok.
3. **API cost slot** hiçbir Settings ekranında yok
   ([[subscription-based-cli-no-cost-dashboard]]).

### Senaryo j — Full backend gate

- [ ] `.venv/bin/python -m pytest packages/mind/tests/
      packages/orchestrator/tests/ packages/body/tests/ -q` → ≥1957 pass.
- [ ] `.venv/bin/python -m ruff check packages/orchestrator/src/
      selffork_orchestrator/dashboard/
      packages/orchestrator/src/selffork_orchestrator/heartbeat/
      config.py packages/orchestrator/tests/dashboard/` →
      All checks passed.
- [ ] `.venv/bin/python -m mypy packages/orchestrator/src/
      selffork_orchestrator/dashboard/settings/
      packages/orchestrator/src/selffork_orchestrator/dashboard/
      settings_router.py packages/orchestrator/src/
      selffork_orchestrator/dashboard/reflex_router.py
      packages/orchestrator/src/selffork_orchestrator/dashboard/
      heartbeat_wire.py packages/orchestrator/src/
      selffork_orchestrator/heartbeat/config.py` → Success.
- [ ] `cd apps/web && npx tsc --noEmit` → clean.

### Senaryo k — audit-god rigorous review

- [ ] `audit-god` agent dispatch — bulgular CRITICAL/MAJOR/MINOR
      sınıflı; CRITICAL = 0 hedef.

### Senaryo l — Commit-ready

- [ ] Memory entry: `project_s4_complete_2026_05_23.md` yazıldı.
- [ ] `MEMORY.md` index güncel.
- [ ] ADR-007 §4 S4 blok "✅ done" damgası.
- [ ] Commit message draft operatöre sunuldu (S-Auto + S-Memory
      formatında).
- [ ] Operatör onayı sonrası tek commit (MANDATE 1).

### S4 sonrası deferred (sonraki sprintlere)

- Settings hot-reload (PUT effect-now) — model endpoint + autonomy
  şu an restart gerektiriyor; S-Vision veya M7 öncesi ek sprint
  adayı.
- Real M7 Reflex training worker — `/train` queue contract zaten
  hazır; worker M7 Reflex sprint'inde.
- Vision adapter inline section (şu an separate page) — operatör
  kararı: separate kalır.
- CLI Agent selection in Settings — S6 (CLI Router) sprint scope.
- Body daemon Settings panel — S-Vision genişletmesi.
- Voice modality Settings panel — S-Vision'da netleşecek.

## S5 — Connections Actions + Provider Auth Alert (ADR-007 §4)

**Hedef:** Connections page sahte button'lar SİL (operatör 2026-05-23:
"hepsi CLI sonuçta gitsin giriş yapsın eşşek değilse"). Telegram bridge
YAML persist (`~/.selffork/settings/telegram.yaml`) + gerçek `setWebhook`
API çağrısı. CLI auth kendi kendine çıkarsa Telegram alert
(ProviderAuthMonitor, cooldown'lı).

**Backend (yeni / upgrade):**

- `TelegramConfig` schema (bot_token + chat_id + mode polling/webhook
  + webhook_url + webhook_secret + soft_confirm_window_hours).
- `~/.selffork/settings/telegram.yaml` YamlSettingsStore.
- `GET /api/settings/telegram` (YAML > env > defaults).
- `POST /api/telegram/setup` upgrade: YAML'a yaz, webhook mode'da
  `setWebhook` Telegram API + secret token + secret YAML'dan resolve,
  chat_id `operators.json` allowlist'e merge.
- `POST /api/providers/{name}/auth-expired` — ProviderAuthMonitor
  Telegram alert (cooldown'lı, AIR alert pattern emsali).
- Server.py refactor: env-based bot_token/mode/webhook_url resolution
  → resolve_telegram_config; lifespan polling-gate `app.state.
  telegram_mode` okur (YAML-only webhook config polling+webhook
  conflict önlenir).
- cli.py `_build_telegram_bridge` resolve_telegram_config kullanır
  (warden + dashboard same source).

**Frontend (`connections/page.tsx` full rewrite):**

- Provider 5 satır: Sign in/Sign out/Test connection/Browser preview
  button'lar SİL; "Subscription: Pro/Plus/Free Tier" hardcoded
  label'lar SİL; her satıra `<cli> login` komut ipucu eklendi.
- Provider auth_expired badge (registry last_error tabanlı).
- Telegram "Connect" button → modal form (bot_token + chat_id + mode
  + webhook_url + webhook_secret + soft_confirm hours).
- Send test + activity table KORUNDU (canlı).

### Senaryo a — Telegram bridge wizard polling mode

1. `selffork ui` başlat (env'de bot_token YOK).
2. UI Connections → "Connect" → modal'da bot_token + chat_id (örn
   12345678) gir, mode=polling, soft_confirm=4. Save.
3. `cat ~/.selffork/settings/telegram.yaml` → bot_token persist.
4. `cat ~/.selffork/operators.json` → chat_ids: [12345678] merge.
5. Orchestrator restart → /api/telegram/status `state=connected`,
   `mode=polling`.

### Senaryo b — Webhook mode + setWebhook API call

1. Wizard'da mode=webhook, webhook_url=https://<host>/api/telegram/
   webhook, webhook_secret=<secret> gir. Save.
2. Backend Telegram setWebhook API'ya gerçek POST atar; başarısızsa
   502 ile geri döner + YAML zaten persist.
3. Inbound `/api/telegram/webhook` çağrısı X-Telegram-Bot-Api-Secret-
   Token check eder (YAML webhook_secret'i resolve ediliyor).
4. Yanlış secret → 401. Boş secret → gate kapalı (legacy).
5. Lifespan: webhook mode → updater polling BAŞLAMAZ (YAML mode
   tabanlı, env değil).

### Senaryo c — Provider auth alert end-to-end

1. `curl -X POST http://127.0.0.1:8765/api/providers/claude_pro/
   auth-expired -d '{"reason":"401 from API"}' -H 'Content-Type:
   application/json'` → 202 + alert YAML resolved bridge'e gönderilir.
2. Telegram'da: "🔐 Auth expired: claude_pro / Reason: 401 from API /
   Run this in your terminal to re-authenticate: claude /login".
3. 1 sn içinde aynı endpoint'e tekrar POST → response
   `cooldown_skipped=true`, Telegram mesajı YOK (5dk cooldown).
4. Connections page'inde claude_pro row'unda kırmızı badge:
   "Auth expired — Self Jr will keep nudging you in Telegram. Run
   `claude /login` to re-authenticate."

### Senaryo d — Connections sahte UI tamamen silinmiş

1. `grep -E "Subscription: Pro|Sign out|Browser preview|Test connection"
   apps/web/app/connections/page.tsx` → sıfır eşleşme.
2. Provider row'larında her button gerçek (login komut hint sadece
   read-only).
3. Telegram bridge "Connect" button → modal canlı; iptal,
   submit, validation hepsi çalışıyor.
4. Activity table real veri (S3 mevcut).

### Senaryo e — Operators.json merge (yeni operatör eklenince)

1. Mevcut `~/.selffork/operators.json` 2 chat_id ile: [111, 222].
2. Wizard chat_id=98765 ile çalıştır.
3. operators.json `chat_ids: [111, 222, 98765]` (merge, clobber yok).
4. default_project_slug korunur.

### Senaryo f — Warden YAML resolve (cross-process consistency)

1. `selffork ui` + wizard tamamla (bot_token YAML'da).
2. Yeni terminal: `selffork run prd.md` başlat.
3. Self Jr destructive eylem isterse warden Telegram bridge'i kullanır
   (resolve_telegram_config tabanlı, env değil).
4. Operator destructive eylem onayı Telegram'da görür.

### Senaryo g — Full backend gate

- [ ] `.venv/bin/python -m pytest packages/mind/tests/
      packages/orchestrator/tests/ packages/body/tests/ -q` → ≥1989 pass.
- [ ] `.venv/bin/python -m ruff check packages/orchestrator/src/
      selffork_orchestrator/dashboard/ packages/orchestrator/src/
      selffork_orchestrator/cli.py packages/orchestrator/tests/
      dashboard/` → All checks passed.
- [ ] `.venv/bin/python -m mypy packages/orchestrator/src/
      selffork_orchestrator/dashboard/provider_auth_monitor.py
      packages/orchestrator/src/selffork_orchestrator/dashboard/
      settings/` → Success.
- [ ] `cd apps/web && npx tsc --noEmit` → clean.

### Senaryo h — audit-god rigorous review

- [ ] `audit-god` agent dispatch — bulgular CRITICAL/HIGH/MEDIUM/LOW/
      INFO sınıflı; CRITICAL = 0 hedef; HIGH bulgularda her biri
      regression test'ine bağlı fix uygulandı.

### Senaryo i — Commit-ready

- [ ] Memory entry: `project_s5_complete_2026_05_23.md` yazıldı.
- [ ] `MEMORY.md` index güncel.
- [ ] ADR-007 §4 S5 blok "✅ done" damgası.
- [ ] Commit message draft operatöre sunuldu.
- [ ] Operatör onayı sonrası tek commit (MANDATE 1).

### S5 sonrası deferred (sonraki sprintlere)

- Snapper layer auth_failed signal otomatik `/auth-expired` POST'a
  fire eder — şu an manuel POST gerek. S6 router veya S7 işine ek.
- Bot token leak self-host CORS scenario — auth middleware ekleme
  S7 veya server self-host hardening sprint'inde.
- Provider sign-in storage_state per-project — M5-E close-out
  görevi ileri sprint'e ertelendi (CLI-native ile çelişki yok ama
  Self Jr "anti-bot trip" fallback'i bir gün gerekirse).
