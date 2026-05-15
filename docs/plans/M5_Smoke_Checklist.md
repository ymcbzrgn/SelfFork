# M5 Body — Operator Deploy Smoke Checklist

> **Tarih:** 2026-05-15
> **Commit:** `7c10b59`
> **Bağlam:** ADR-005 ACCEPTED — M5 Body pillar kod tarafı %100 done. Bu checklist operator manuel smoke + R1 vision eval gate'i için.
> **Hedef sıralama:** 1 → 9 sırayla; bir senaryo fail ederse sonraki senaryoya geçilmez, durulur ve rapor edilir.
> **R1 Gate:** Final adımda `pytest benchmarks/m5_vision_eval/run_eval.py` accuracy ≥ %85 olmalı. Aksi halde **Bouncing Back** (ROADMAP §M5): vision drivers M6'a regress.

---

## 0. Ön-Koşullar

Tüm senaryolardan ÖNCE bir kere çalıştır:

```bash
cd /Users/yamacbezirgan/Projects/SelfFork
bash infra/install/m5_deploy_prereqs.sh --check   # önce dry-run
bash infra/install/m5_deploy_prereqs.sh           # gerçek kurulum (operator onayıyla)
```

Vision adapter konfigürasyonu (3 yol — herhangi biri yeterli):

1. **Default** (kod-built-in): MLX `mlx-community/gemma-4-E2B-it-4bit` @ `:8080`, Ollama `gemma4:e2b-q4_K_M` @ `:11434`. Hiçbir şey yapmamak yeterli; smoke 1 doğrudan bu defaults'la çalışır.
2. **YAML** (`~/.selffork/config.yaml`):
   ```yaml
   vision:
     mlx_model_id: mlx-community/gemma-4-E2B-it-4bit
     mlx_server_url: http://127.0.0.1:8080
     ollama_model_tag: gemma4:e2b-q4_K_M
     ollama_host: http://127.0.0.1:11434
     auto_detect: true
   ```
3. **Cockpit Settings → Vision** (senaryo 9 ile birlikte test edilir): `/cockpit/settings/vision` → "Auto-detect models" → dropdown → "Apply".

Manuel prereq:

- macOS Sistem Tercihleri → Gizlilik ve Güvenlik → **Erişilebilirlik** → terminal/iTerm onaylı (M5 #2 için zorunlu).
- macOS Sistem Tercihleri → Gizlilik ve Güvenlik → **Ekran Kaydı** → terminal/iTerm onaylı (screenshot driver için).
- Tailscale login: `tailscale up --authkey=<key>` (M5 #8 için zorunlu; tek hostta test edilirse atlanır).
- Model dosyaları: Hugging Face'ten indir — `huggingface-cli download mlx-community/gemma-4-E2B-it-4bit`. Ollama tarafı: `ollama pull gemma4:e2b-q4_K_M`.

> ⚠️ **MLX PLE bug uyarısı (2026-04 sonrası)**: `mlx-community/gemma-4-E2B-it-4bit` ve diğer naive MLX 4-bit quantization'lar Per-Layer Embedding katmanlarını da quantize ediyor → bozuk output. Belirti: vision decision tutarsız / nonsense JSON. R1 eval ≥%85'in çok altında. Workaround: `mlx-community/gemma-4-e2b-it-OptiQ-4bit` (PLE-safe) veya `FakeRockert543/gemma-4-e2b-it-MLX-4bit` (text-only baseline) ile probe et; vision için OptiQ kullanmaya geçilebilir. Cockpit Settings → Vision → "Auto-detect" ile elinde yüklü olan tüm variantları listele, yan yana eval'le.

---

## 1. Vision Pipeline Canlı (Gemma 4 E2B Q4_0)

**Entry:** `packages/body/src/selffork_body/vision/runtime.py:178` — `VisionOrchestrator`

**Prereq (ayrı terminal, smoke süresince açık tut):**

```bash
# Aktif vision config'i sorgula (Cockpit veya YAML değişimi sonrası source-of-truth):
curl -s http://localhost:8000/api/settings/vision | .venv/bin/python -m json.tool

# mlx_vlm.server config'teki model_id ile başlat:
MODEL_ID=$(curl -s http://localhost:8000/api/settings/vision | .venv/bin/python -c "import json,sys; print(json.load(sys.stdin)['mlx_model_id'])")
python -m mlx_vlm.server --model "$MODEL_ID" --port 8080
```

**Auto-detect doğrulama (Cockpit ile aynı):**

```bash
curl -s -X POST http://localhost:8000/api/settings/vision/detect | .venv/bin/python -m json.tool
# Beklenen: {"mlx_available": true, "mlx_models": [...]} — mlx_models içinde
# config'teki mlx_model_id görünmeli; aksi halde server farklı modelle başlatılmış.
```

**Smoke komut (config-driven):**

```bash
.venv/bin/python -c "
import asyncio
from selffork_body.vision.runtime import VisionOrchestrator, MlxVlmAdapter
from selffork_shared.config import load_settings

async def main():
    cfg = load_settings().vision
    adapter = MlxVlmAdapter.from_config(cfg)
    orch = VisionOrchestrator(tier1=adapter, audit_emit=lambda c, p: print(c, p))
    with open('docs/screenshots/m5_smoke_fixture.png', 'rb') as f:
        png = f.read()
    d = await orch.decide(screenshot=png, goal='locate the Sign In button')
    print(d)

asyncio.run(main())
"
```

**Beklenen:** `VisionDecision(action='click', target='Sign In button', bbox=(x,y,w,h)|None, confidence>0, tier=1, duration_ms<5000)` print eder; `body.vision.query` audit event basılır.

**Pass:** `tier=1` döner + `duration_ms < 5000` + decision fields parse edilebilir.
**Fail:** `RuntimeError`, server-not-reachable, `json.JSONDecodeError` (prompt drift).
**Risk:** mlx_vlm server up değilse 502 → ön-koşul dosya kontrolü.

---

## 2. macOS Desktop Driver (AX + screencapture)

**Entry:** `packages/body/src/selffork_body/drivers/desktop/macos/driver.py:28` — `MacOSDesktopDriver`

**Prereq:**
- TCC izinleri (Erişilebilirlik + Ekran Kaydı) açık.
- `selffork_body/drivers/desktop/macos/tcc_check.py:28` ile `AXIsProcessTrusted()` true dönmeli.

**Smoke:**

```bash
.venv/bin/python -c "
import asyncio
from selffork_body.drivers.desktop.macos.driver import MacOSDesktopDriver
from selffork_body.drivers.desktop.macos.applescript_runner import AppleScriptRunner

async def main():
    drv = MacOSDesktopDriver()
    await drv.start()
    ar = AppleScriptRunner()
    await ar.run('tell application \"Finder\" to activate')
    png = await drv.screenshot()
    with open('/tmp/m5_macos_smoke.png', 'wb') as f:
        f.write(png)
    print('OK', len(png), 'bytes')

asyncio.run(main())
"
```

**Beklenen:** Finder foreground'a gelir; `/tmp/m5_macos_smoke.png` ≥ 50 KB; AX permissions dialog ilk açılışta kullanıcıdan onay isteyebilir.
**Pass:** PNG > 50 KB + macOS sistem hata dialogu yok.
**Fail:** `AXIsProcessTrusted()` false → izin yenile; `screencapture` exit !=0 → screen recording izni yenile.

---

## 3. Web Driver (Playwright Chromium)

**Entry:** `packages/body/src/selffork_body/drivers/web/playwright_driver.py:31` — `PlaywrightWebDriver`

**Prereq:** `uv pip install playwright && playwright install chromium`

**Smoke (5 alt-senaryo):**

```bash
.venv/bin/python -c "
import asyncio
from selffork_body.drivers.web.playwright_driver import PlaywrightWebDriver

async def main():
    drv = PlaywrightWebDriver(headless=False)
    await drv.start()
    for url in ['https://www.google.com', 'https://github.com/pulls', 'https://calendar.google.com']:
        await drv.goto(url)
        png = await drv.screenshot()
        loc = await drv.evaluate('() => location.href')
        print(url, '→', loc, len(png), 'bytes')
    await drv.stop()

asyncio.run(main())
"
```

**Alt-senaryolar (manuel):**
- (a) Google.com — yukarıdaki komutta otomatik.
- (b) GitHub PR listesi — yukarıdaki komutta otomatik.
- (c) Google Calendar — yukarıdaki komutta otomatik (login isteyebilir → providers UI'da OAuth ile bağlanmış olmalı).
- (d) OAuth callback (provider sign-in akışı) — senaryo 7'de detaylı.
- (e) Form submit — manuel: `https://httpbin.org/forms/post` aç + form doldur + submit + ekran al.

**Pass:** Üç URL için PNG > 30 KB, URL doğru.
**Fail:** Chromium başlamıyor → `playwright install chromium` tekrar; `allowed_domains` gate kapalıysa navigation watchdog tetiklenir.

---

## 4. Android Driver (docker-android + mobile-mcp + UIAutomator2)

**Entry:** `packages/body/src/selffork_body/drivers/android/__init__.py:36` — `AndroidDriver`

**Prereq:**
- `docker run -d -p 6080:6080 -p 5555:5555 budtmo/docker-android:emulator_11.0` (veya runtime image)
- `mobile-mcp` server 8000 portunda: `npx -y @mobilenext/mobile-mcp` (Yamaç tercih ederse `uvx`).
- `adb` kurulu (Android Platform Tools).

**Smoke:**

```bash
.venv/bin/python -c "
import asyncio
from selffork_body.drivers.android import AndroidDriver

async def main():
    drv = AndroidDriver(runtime='docker')
    await drv.start()
    # Settings app launch (mobile-mcp veya adb shell üzerinden)
    await drv.mcp.launch_app('com.android.settings')
    png = await drv.screenshot()
    with open('/tmp/m5_android_smoke.png', 'wb') as f:
        f.write(png)
    print('OK')
    await drv.stop()

asyncio.run(main())
"
```

**Pass:** Settings ekranı yakalanır + PNG > 30 KB.
**Fail:** docker-android boot incomplete (`wait_for_boot()` timeout); mobile-mcp 8000'de yok → server check.
**Risk:** `click` bbox zorunlu (line 76-77); vision sonucu olmadan click denenirse `ValueError`.

---

## 5. iOS Simulator Driver (Appium XCUITest)

**Entry:** `packages/body/src/selffork_body/drivers/ios/__init__.py:26` — `IosDriver`

**Prereq:**
- Xcode + iOS 17.2 simulator runtime.
- Appium server `:4723`: `appium --base-path /wd/hub` (ayrı pencere).
- `xcrun simctl list devices` ile booted simulator var.

**Smoke:**

```bash
.venv/bin/python -c "
import asyncio
from selffork_body.drivers.ios import IosDriver

async def main():
    drv = IosDriver(runtime='sim', ios_version='17.2')
    await drv.start()
    await drv.simulator.app_launch('com.apple.mobilesafari')
    png = await drv.screenshot()
    with open('/tmp/m5_ios_smoke.png', 'wb') as f:
        f.write(png)
    print('OK')
    await drv.stop()

asyncio.run(main())
"
```

**Pass:** Safari açılır + PNG > 30 KB.
**Fail:** `xcrun simctl` simulator down → manuel boot; Appium 4723 timeout → server start kontrolü.

---

## 6. tmux Driver — M3 Regression (5 CLI canlı)

**Entry:** `packages/orchestrator/src/selffork_orchestrator/cli.py:90` — `selffork run`; `:211` — `selffork run-many`

**Prereq:** 5 PRD test dosyası `tests/fixtures/prd/smoke_{1..5}.md`; tüm CLI'ler erişilebilir (claude, codex, gemini, opencode, minimax).

**Smoke:**

```bash
# Tek session her CLI ile:
for agent in claude_code codex gemini_cli opencode minimax_cli; do
  selffork run tests/fixtures/prd/smoke_1.md --agent $agent --timeout 60 || echo "FAIL: $agent"
done

# Paralel (run-many):
selffork run-many tests/fixtures/prd/smoke_{1..5}.md
```

**Pass:** 5 CLI ayrı ayrı session başlatır + `[SELFFORK:DONE]` sentinel ile sonlandırır.
**Fail:** CLI provider auth expired → senaryo 7'ye dön; round-loop timeout.

---

## 7. Provider Auth UI (Cockpit sign-in)

**Entry:** `apps/web/app/cockpit/providers/page.tsx` + `dashboard/provider_router.py:121`

**Prereq:** Backend ayağa: `selffork dashboard` veya doğrudan FastAPI uvicorn. Frontend: `cd apps/web && pnpm dev` (port 3000).

**3 alt-senaryo:**

| Provider | URL | Beklenen |
|---|---|---|
| codex | `http://localhost:3000/cockpit/providers` → Codex kartı → "Sign In" | Browser açılır, OAuth flow, storage_state JSON kaydedilir |
| gemini-cli | Aynı sayfa → Gemini kartı → "Sign In" | Aynı |
| opencode | Aynı sayfa → opencode kartı → "Sign In" | Aynı |

**API smoke (parallel):**

```bash
curl -s http://localhost:8000/api/providers | jq .
# Beklenen: 5-provider list, status enum (connected/disconnected/expired/expiring_soon)
curl -X POST http://localhost:8000/api/providers/codex/sign_in_start | jq .
# Beklenen: SignInStartResponse (login_url veya local_browser flow)
```

**Pass:** 3 provider connected duruma geçer; storage_state ~/.selffork/storage_states/<provider>.json kaydedilir.
**Fail:** OAuth callback URL mismatch; storage_state save fail (warden gate); Cockpit "Sign In" butonu 500.

---

## 8. Daemon Round-Trip (Go cross-platform)

**Entry:** `packages/body/daemon/cmd/selffork-daemon/main.go:32`

**Prereq:**
- macOS host: `cd packages/body/daemon && make macos-arm64` (binary `dist/selffork-daemon-darwin-arm64`)
- Linux host (varsa): `make linux-amd64`
- HMAC secret: `export SELFFORK_DAEMON_SECRET="dev-secret-change-in-prod"`

**Smoke (tek host — round-trip):**

```bash
# Pencere 1 — backend:
selffork dashboard --host 0.0.0.0 --port 8000

# Pencere 2 — daemon:
cd packages/body/daemon
SELFFORK_DAEMON_SECRET="dev-secret-change-in-prod" \
  ./dist/selffork-daemon-darwin-arm64 \
  --orchestrator-url http://localhost:8000 \
  --heartbeat-interval 5s \
  --machine-id $(hostname)
```

**Pass:**
- `POST /api/fleet/register` → 201 + `auth_key`.
- Her 5 saniyede `POST /api/fleet/heartbeat` → 204.
- Cockpit `/cockpit/fleet` tab'ında machine_id görünür.

**Fail:** 401 → HMAC mismatch; 409 → re-register without rotation (iter list madde 14).
**Risk (cross-host):** Tailscale up değilse work Ubuntu'dan home Mac'e dial fail; firewall 8000 blokeli olabilir.

---

## 9. Cockpit Full Matrix (4 M4 + 3 M5 tab)

**Prereq:** Backend + frontend dev server (senaryo 7 ile aynı).

**Tab kontrol listesi:**

| # | Tab | URL | Beklenen |
|---|---|---|---|
| M4-1 | Mission | `/cockpit` (default) | Mission/PRD listesi |
| M4-2 | Run | `/cockpit/run` | Aktif/biten run grid |
| M4-3 | Chat | `/cockpit/chat/<session_id>` | Round-loop transkript |
| M4-4 | Context | `/cockpit/context` | Mind T1/T2/T3 viewer |
| M5-1 | Body | `/cockpit/body` | Driver/screenshot canlı feed |
| M5-2 | Providers | `/cockpit/providers` | 5-provider auth grid (senaryo 7) |
| M5-3 | Fleet | `/cockpit/fleet` | Daemon machine_id grid (senaryo 8) |
| M5+1 | Settings/Vision | `/cockpit/settings/vision` | MLX+Ollama model dropdown + "Auto-detect" + "Apply" |

**M5+1 alt-senaryo:**

1. `/cockpit/settings/vision` aç.
2. "Auto-detect models" butonuna tıkla.
3. MLX bölümünde "available" yeşil rozet + `mlx_models` dropdown listesi (mlx_vlm.server'da yüklü modeller).
4. Ollama bölümünde "available" veya "unreachable" (Ollama çalışıyorsa available olmalı).
5. Bir model swap dene (örn. `mlx-community/gemma-4-E4B-it-4bit`) → "Apply".
6. Yeşil banner: "Saved. Restart any in-flight sessions...".
7. `~/.selffork/config.yaml` aç, `vision:` bölümü güncellenmiş.
8. Senaryo 1 smoke komutunu tekrar çalıştır: yeni model_id picked up.

**Pass:** 7 tab birinden ötekine geçiş sırasında 500/404 yok; WebSocket reconnect smooth.
**Fail:** Backend health check fail; CORS hatası → `next.config.js` proxy gözden geçir.

---

## R1 Vision Eval (Final Gate)

**Entry:** `benchmarks/m5_vision_eval/run_eval.py` (üretim aşamasında)

**Prereq:**
- `benchmarks/m5_vision_eval/index.jsonl` 30 task ile dolu.
- `benchmarks/m5_vision_eval/tasks/<task_id>/{screenshot.png, goal.txt, expected_action.json}` her task için mevcut.
- `python -m mlx_vlm.server` ayakta (senaryo 1 prereq).

**Komut:**

```bash
.venv/bin/python -m pytest benchmarks/m5_vision_eval/run_eval.py -v \
  --tb=short \
  --json-report --json-report-file=/tmp/m5_r1_eval.json
```

**Pass kriteri:**
- `accuracy >= 0.85` (action enum match AND target case-insensitive substring match AND bbox IoU ≥ 0.5)
- Exit 0
- `body.vision.query` audit JSONL `~/.selffork/audit/<date>.jsonl` içinde 30 satır

**Fail kriteri (Bouncing Back trigger):**
- `accuracy < 0.85` → **Vision drivers M6'a regress** (ROADMAP §M5 revize)
- Operator bildirimi: failed task'ların IDs + tier history + bbox/target/action breakdown raporu

---

## Sonuç Raporu Şablonu

Tüm 9 senaryo + R1 eval sonrası operator şunu doldurur:

```
SelfFork M5 Smoke Report — <YYYY-MM-DD>

Senaryolar:
  1. Vision Pipeline    : [PASS|FAIL] — notlar
  2. macOS Desktop      : [PASS|FAIL] — notlar
  3. Web Driver         : [PASS|FAIL] — notlar (a/b/c/d/e)
  4. Android Driver     : [PASS|FAIL] — notlar
  5. iOS Simulator      : [PASS|FAIL] — notlar
  6. tmux M3 Regression : [PASS|FAIL] — notlar (claude/codex/gemini/opencode/minimax)
  7. Provider Auth UI   : [PASS|FAIL] — notlar (codex/gemini/opencode)
  8. Daemon Round-Trip  : [PASS|FAIL] — notlar
  9. Cockpit Full       : [PASS|FAIL] — notlar (M4-1..4, M5-1..3)

R1 Vision Eval:
  Accuracy : 0.XX
  Pass count : XX / 30
  Failed tasks : [list of task_id]
  Decision : [DEPLOY|BOUNCING BACK]
```

---

## Referanslar

- ADR-005 §audit-fix wave — 41 iter maddesi (M5+/M6 patch listesi)
- `docs/plans/M5_Body_Plan.md` §3.5 — R1 dataset specs
- `packages/body/README.md` — driver matrix overview
- Memory: `[[gemma4-always]]`, `[[project_m5_complete_2026_05_15]]`, `[[feedback_warden_default_deny]]`
