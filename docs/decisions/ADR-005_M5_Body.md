# ADR-005 — M5 Body (Cross-Platform Daemon + Vision Drivers + Provider Auth UI)

**Tarih:** 2026-05-10
**Milestone:** M5 — Body
**Status:** ACCEPTED (operator approved 2026-05-10)
**Supersedes:** `docs/ROADMAP.md` §7 "Driver Roadmap (Body)" — vision driver tier kısıtı + ROADMAP M5 scope
**Builds on:** ADR-001 (MVP v0 §4 packages/body skeleton + §14.9 sandbox/audit), ADR-002 (Mind), ADR-003 (M3 CLI Surfing), ADR-004 (M4 Cockpit)

---

## Karar

M5 = **Body Pillar (Vision + Cross-UI Control)** — üç katmanlı bir bütün:

1. **Cross-platform Daemon** (ROADMAP §M5 scope) — operator'ın home Mac'inden iş Windows + Ubuntu makinelerine "beyni uzatma"; macOS / Windows / Ubuntu daemon binary'leri; Tailscale ACL; Cockpit Fleet view; location-aware slider; tmux desktop CLI driver. Exit: p95 < 2sn round-trip.
2. **Vision-Driven UI Drivers** (handoff scope) — Gemma 4 E2B vision pipeline ile mobile (Android + iOS simulator) + web + macOS desktop + tmux desktop; **DOM/AX-tree + screenshot hibrit** paradigması; CDP-first web stack (Playwright + browser-use referans); native AX-tree primary desktop; docker-android+mobile-mcp+uiautomator2 Android; Appium XCUITest+WDA+go-ios iOS sim; clippy Electron+llama.cpp building block macOS desktop shell.
3. **Sandbox + Permission Warden + Provider Auth UI** (cross-cutting) — `packages/body/sandbox/` action-level warden (orchestrator subprocess/Docker sandbox'ından **ayrı concern**); 3-mod (read_only / workspace_write / danger_full_access) + 4-tier risk_tier (T0/T1/T2/T3); 5 yeni `body.*` AuditCategory; OS-tier (macOS seatbelt + bubblewrap + gVisor cloud); Provider Auth UI cockpit 5. tab — browser-driven OAuth orchestration ile auth-only kuralı (API key ASLA, sadece subscription OAuth).

**Süre:** 6-8 hafta — ROADMAP M5 (3-4 hafta daemon) + handoff M5 (4-6 hafta vision drivers) birleşik.

**Tek model varsayımı:** Gemma 4 E2B-it Q4_0 (mlx_vlm runtime, native pointing + bbox JSON output). ROADMAP §7 "Full Vision tier 26B A4B" gereksinimi **revize edildi** — Ajan 7 (vision prompting research) ve Ajan 8 (browser-use Ollama integration) bulgularına göre E2B native pointing yeterli. Q4_0 + SoM henüz public benchmark yok, M5 implementation'da head-to-head eval edilecek.

**Öğrenme yaklaşımı (Karpathy disiplini):** "Minik scope, enterprise quality" — her driver ilk gün pluggable, audit-coverage tam, redaction-safe, kill-switch'li. iOS real device + Linux/Windows desktop drivers + Skyvern AGPL boundary + scraping katmanı + stealth/CAPTCHA = M5 değil, M6/M7'ye iter (alt §Sınırlamalar).

---

## Mimari kararlar

### M5-A — Body Daemon Layer (cross-platform CLI extension)

**Amaç:** Operator'ın home orchestrator'ı uzaktaki bir makineye (work Windows / work Ubuntu) bağlanıp lokal CLI'yı sürebilir; lokal cihaz state'i ve action'lar Tailscale üzerinden home cockpit'te canlı.

**Paket:** `packages/body/daemon/`

**Karar:** Go binary preferred (Python+PyInstaller fallback). **Tek static binary per platform** distribution kolaylığı için. Implementation dili tartışması:
- **Pro Go:** Apple notarize/Microsoft Authenticode/Linux .deb/.rpm tek artifact; Tailscale resmi Go SDK; cross-compile makul (`GOOS=darwin GOARCH=arm64`).
- **Pro Python:** Mevcut codebase Python; PyInstaller ile single-file dist çalışır ama dosya 50-100MB+; Apple notarize friction.
- **Karar:** Go (Tailscale Go SDK + binary boyutu + cross-platform notarization paketleme avantajı). Python wrapper'la da köprülenebilir (daemon'dan orchestrator'a JSON-RPC over Tailscale).

**Submodüller:**
- `packages/body/daemon/cmd/selffork-daemon/` — Go entry point (main).
- `packages/body/daemon/internal/heartbeat/` — periodic ping (15sn cadence) + reconnect (exponential backoff: 1s → 2s → 5s → 15s → 30s, max 60s).
- `packages/body/daemon/internal/cli_bridge/` — local tmux/PowerShell/screen pane control.
- `packages/body/daemon/internal/state_reporter/` — terminal state → home orchestrator (JSONL stream over WebSocket-on-Tailscale).
- `packages/body/daemon/internal/command_intake/` — orchestrator → daemon prompts (signed payload).

**Build matrix:**
- macOS arm64 + amd64 → Homebrew tap + Apple Developer ID notarize + DMG/ZIP.
- Windows x64 → Squirrel.Windows + Azure Trusted Signing + .msi (clippy `forge.config.ts:54-59,207-227,448-483` pattern referans).
- Ubuntu x64 + arm64 → .deb + APT repo (apt.selffork.dev).

**Tailscale ACL (ROADMAP M-1'de validate edildi, M5'te codify):**
- Home Mac (orchestrator) → work-windows + work-ubuntu (CLI ports + daemon WS).
- Per-machine `tag:selffork-daemon` ACL group; her daemon bir Tailscale auth key (rotated 30 gün).
- ACL `tags.json` `infra/tailscale/acl.json`'a versiyonlanır.

**Cockpit Fleet view:**
- Yeni route: `/cockpit/fleet` — daemon list (machine_id, hostname, online/offline, latency_ms, last_seen, version).
- Daemon WS endpoint: `/api/fleet/stream` — heartbeat broadcast (M-1 WS protocol M4'te kuruldu, ekleme katmanı).
- **Location-aware slider:** daemon her connect'te `host_identity` payload gönderiyor (`{machine: "home-mac"|"work-windows"|"work-ubuntu", location_tier: "home"|"work"}`). Cockpit slider state'i `useFleetStore` (Zustand 5. slice) okuyup auto-shift yapıyor (home=7, work=4 default — `selffork.yaml`'de configurable).

**Tmux desktop driver (ROADMAP §7 + §M5):**
- `packages/body/drivers/desktop/tmux/` — daemon-host machine üzerinde Claude Code / OpenCode / Gemini / Codex / Minimax CLI control via tmux send-keys + capture-pane.
- M3 snapper fleet pattern reuse: 1sn cadence atomic file write `~/.selffork/cli-state/<cli>.json` (already implemented in `packages/orchestrator/.../snappers/`).
- Daemon snapper sonuçlarını orchestrator'a stream'liyor; cockpit Run tab'ı remote daemon'lardan gelen state'i merge gösteriyor.

**Exit kriteri:**
- Daemon round-trip (prompt→execute→result over Tailscale) **p95 < 2 saniye**.
- Daemon reconnect: 1 dakika içinde recovery (network drop sonrası).
- Daemon startup: < 5 sn.
- Daemon idle CPU: < %5; RAM: < 100MB.
- macOS + Windows + Ubuntu daemon installer'ı çalışıyor.
- Demo: home Mac → work Ubuntu daemon → CLI lane → result home cockpit'te canlı.

---

### M5-B — Vision Pipeline (Gemma 4 E2B multimodal)

**Amaç:** Gemma 4 E2B-it Q4_0'ı mlx_vlm üzerinden screenshot → tool-call action loop'una bağla. <2sn end-to-end target.

**Pre-requirement migration (LLMRuntime multimodal):**

Mevcut `packages/orchestrator/src/selffork_orchestrator/runtime/base.py:24-27`:
```python
ChatMessage = dict[str, str]
```

Migration → `dict[str, str | list[ContentPart]]`. `ContentPart` = `Literal["text"] + str` veya `Literal["image_url"] + url/path` veya `Literal["image_b64"] + bytes`. OpenAI vision protocol'üyle compat.

**Etkilenen dosyalar (impact perimeter Ajan 12 raporu):**
- `runtime/base.py:24-27,91-93` — ChatMessage tip + `LLMRuntime.invoke` imza extension
- `runtime/{ollama,llama_cpp,vllm,mlx_server}.py` — her runtime backend'in vision parity'si (MLX server zaten `mlx_vlm.server` ile vision-ready, diğer 3 backend için fallback graceful — `raises NotImplementedError` veya text-only auto-strip).
- 4 CLIAgent (`claude_code.py`/`gemini_cli.py`/`codex.py`/`opencode.py`/`minimax_cli.py`) bu tipi tüketmiyor — risk düşük.

**Vision pipeline modülleri (`packages/body/vision/`):**

- `vision/screenshot.py` — cross-platform screenshot capture:
  - macOS: `screencapture -x -t png` subprocess + AVFoundation fallback (Quartz `CGWindowListCreateImage`); Mac Accessibility/Screen Recording TCC permission gating.
  - Windows: `screenshot` via PowerShell `Add-Type System.Drawing` veya `mss` (Python).
  - Linux: `scrot`/`grim` (Wayland) / `xdg-desktop-portal-screencast` (Wayland fallback).
  - iOS sim: `xcrun simctl io booted screenshot --type=png /tmp/x.png`.
  - Android: `adb shell screencap -p /sdcard/x.png && adb pull` (uiautomator2 wrapper).
  - Web (browser): Playwright `page.screenshot(full_page=True, type="png")`.

- `vision/preprocess.py` — image preprocessing:
  - Aspect-ratio preserving resize, longer edge **1024-1280** (Gemma 4 multiple-of-48 kuralı, Datature CV guide referans).
  - Token budget knob: **default 280**, high-density UI 560 (`mlx_vlm` `--num-image-tokens` parametresi).
  - ROI crop opsiyonel (target bbox known ise sub-image inference için).
  - Before/after delta image: state-change verification için (action sonrası screenshot - öncesi); LMM'e "did anything change?" sentinel sorusu (Tier-2 verification).
  - Annotation overlay: cursor mark + highlight (DOM/AX-tree bbox biliniyorsa), debug için.

- `vision/prompt.py` — prompt strategy:
  - **Default (Tier-1):** Locate-by-label JSON output. Prompt iskeleti: `"Return JSON: {action: 'click'|'type'|'swipe'|'scroll'|'wait', target: <element-description>, bbox: [x,y,w,h], confidence: 0..1, reason: <short>}"`. Gemma 4 native pointing + bbox JSON yetenekli (HF blog gemma4 + ai.google.dev/gemma/docs/capabilities/vision); ekstra preprocessing yok.
  - **Tier-2 (fallback):** Tier-1 confidence < 0.7 ise + ROI crop + token budget 560'a bump + (DOM/AX-tree mevcut platformlarda) accessibility hint inject.
  - **Tier-3 (last resort):** SoM (Set-of-Marks Microsoft Research arxiv 2310.11441) overlay, sadece web (browser-use buildDomTree.js highlight) ve iOS sim (AX flatten). **NOT default** — Q4_0'da SoM henüz tested değil; Yamaç_Jr_Nano_Kararlar.md güncelleme bekliyor.

- `vision/runtime.py` — `MultimodalLLMRuntime` adapter:
  - `invoke_with_images(messages: list[ChatMessage], images: list[bytes | Path]) -> str`.
  - MlxServerRuntime path (Apple Silicon): mlx_vlm server'a multipart POST (resmi `mlx-vlm.server`).
  - Linux server-side: vLLM `--model mlx-community/gemma-4-E2B-it` parity; Ollama `ollama.AsyncClient.chat(images=[...])` (Ajan 8 verify edilmesi gerek — Gemma 4 Ollama vision compat bilinmiyor; M5 implementation öncesi `selffork-researcher` ile doğrulama).

**Latency budget (NEEDS VERIFICATION — gerçek M5 ölçümünde valide edilecek):**
- Image encode (150M SigLIP, 280 tokens): ~150-300ms (FastVLM benzer encoder ekstrapolasyon).
- Prefill 280 image-token + ~100 prompt-token: ~100-200ms (Apple Silicon Metal).
- Decode 50-100 token JSON: ~300-1500ms (M5 Max 158 tok/s, M3 ~50-80 tok/s).
- **Toplam tahmin:** 1.0-2.5 sn. Hedef p95 < 2sn için decode token sayısı **minimal JSON ile sıkı tutulmalı** (≤50 token).

**Audit emit:**
- Her vision call sonrası `body.vision.query` AuditCategory ile JSONL satırı: `{vision_handle_id, image_bytes_path (binary değil — disk reference), prompt_template_id, output_json, duration_ms, token_count, confidence}`.

---

### M5-C — Drivers

#### M5-C1 — Web driver (`packages/body/drivers/web/`)

**Karar:** Hibrit DOM-first, vision-fallback paradigması (browser-use referans alınır, kod kopyalanmaz). Skyvern **AGPL-3.0 — kod kopyalama YASAK**, sadece architectural pattern referansı.

**Stack seçimi:**
- **Birinci tercih:** Playwright (Python) + `cdp-use==1.4.5` (browser-use'un kullandığı CDP wrapper) + Stagehand v3 (MIT) **opsiyonel** — Stagehand `act/extract/observe/agent` primitifleri Playwright Page object'ine ekleniyor (vendor-lock test M5 implementation öncesi: Browserbase olmadan tamamen lokal Playwright + lokal LLM ile çalışma path'i kod-doğrulanmalı). 16 ajan ARGE'si Stagehand path'ini destekliyor (DOM+vision hybrid + replay caching + ~30% cost düşüşü).
- **İkinci tercih:** Playwright + custom DOM extraction (browser-use `buildDomTree.js` paterni — Apache 2.0 modify+attribute kuralında reimplement). Stagehand vendor-lock'unu kabullenmiyorsak.
- **Reddedilen:** browser-use'un kendisi (MIT — kullanılabilir ama cloud sandbox + telemetry coupling); Skyvern (AGPL-3.0 contamination); LaVague (compile-to-code, audit edilemez); Anthropic Computer Use saf-vision (12-17pt benchmark gerisi).

**Action surface:**
```
class WebDriver:
    async def goto(url: str)
    async def click(selector: str | bbox: tuple[int,int,int,int])
    async def type(selector: str, text: str)
    async def select_option(selector: str, value: str)
    async def scroll(direction: Literal["up","down","top","bottom"], amount: int = 300)
    async def screenshot() -> bytes  # PNG, full_page default
    async def wait_for(selector: str, timeout: float = 5.0)
    async def evaluate(js_code: str) -> Any  # AUDIT: high-risk; T2 warden gate
    async def storage_state_save(path: Path)  # provider auth persist
    async def storage_state_load(path: Path)
```

**Locator strategy fallback chain (Ajan 3 öneri):**
```
1. Playwright accessibility tree query (deterministik, fastest)
2. DOM selector (CSS/role/label) — Stagehand observe / browser-use buildDomTree
3. Gemma 4 vision (canvas, image-only UI, AX failure cases)
4. Manual intervention prompt → Provider Auth UI (anti-bot trip)
```

**`storage_state` per provider (Provider Auth UI ile entegrasyon):**
- Path: `~/.selffork/projects/<slug>/auth/<provider>.json` (orphan session için `~/.selffork/auth-cache/<provider>.json`).
- 30sn auto-save watchdog (browser-use `storage_state_watchdog.py:25-86` paterni — reimplement, kopya değil).
- Cookie expire (default 24h) için lazy "401 → re-auth flow" akışı; proactive re-auth M6'a iter.

**SecurityWatchdog (browser-use pattern, reimplement):**
- `allowed_domains` list per session.
- Navigation öncesi check + redirect-after check + new-tab close.
- Block edilen URL'de `about:blank`'a kıvırma; audit emit `body.permission.deny`.

**Web driver paketleme:**
- `body/drivers/web/playwright_driver.py` — ana implementation
- `body/drivers/web/stagehand_adapter.py` — Stagehand opsiyonel layer (vendor-test M5 prereq)
- `body/drivers/web/security_watchdog.py` — domain allowlist
- `body/drivers/web/storage_state.py` — auth persistence
- `body/drivers/web/dom_extractor.py` — buildDomTree-pattern reimpl

**Audit emit:**
- `body.driver.start{driver: "web", session_id, browser: "chromium"|"firefox"|"webkit"}`
- `body.action.invoke{action_type, target_selector, bbox?, args}`
- `body.action.executed{action_type, duration_ms, status}`
- `body.action.failed{action_type, exception_class, retry_count}`

#### M5-C2 — Android driver (`packages/body/drivers/android/`)

**Stack (Ajan 2 + Ajan 10 sentez):**
- **Katman 0 (sandbox):** docker-android (Apache 2.0, budtmo) — Android 9-14 emulator container. Pro headless sponsor-locked; standart imaj M5 single-pane dev için yeterli; paralel session **M5 değil M6** (sponsor lock).
- **Katman 1 (action surface):** mobile-mcp (Apache 2.0, mobile-next) — MCP server protocol; tap/swipe/long-press/type/screenshot/install APK; SelfFork tool registry'siyle 1:1 örtüşüyor (memory `project_jr_tool_protocol`).
- **Katman 2 (low-level + Gemma vision feeder):** uiautomator2 (MIT, openatx) — ham screencap → numpy/PIL pipeline; mobile-mcp a11y-tree dönmediği canvas/oyun/webview pixel-perfect senaryolar için.

**Reddedilenler:**
- Detox (RN-only, scope dışı), Maestro (test framework, agent runtime için yanlış katman), Appium-UIA2 (JVM/Node overhead — mobile-mcp modern kuzeni), Frida (wxWindows lisans-ish copyleft, M5 default değil — opsiyonel deep-app probing plugin), Genymotion (proprietary).

**Action surface:**
```
class AndroidDriver:
    async def tap(x: int, y: int)
    async def long_press(x: int, y: int, duration_ms: int = 800)
    async def swipe(start_x, start_y, end_x, end_y, duration_ms: int = 250)
    async def type_text(text: str)
    async def press_key(key: Literal["back","home","menu","app_switch"])
    async def launch_app(package: str)
    async def install_apk(path: Path)  # T2 warden gate
    async def screenshot() -> bytes
    async def dump_a11y_tree() -> dict  # mobile-mcp wrapped
    async def adb_shell(command: str)  # T2 warden gate, audit raw cmd
```

**Runtime modes:**
- `dev`: docker-android container (default M5).
- `physical`: USB ADB tunneling (operator opt-in, M5 demo'da yer alır).
- `cloud`: Genymotion-paid ya da AWS Device Farm — **M5 dışı** (proprietary, scope dışı).

**Audit emit:**
- `body.driver.start{driver: "android", runtime: "docker"|"physical", device_id, android_version}`
- Standart action.* events (T1/T2 risk_tier işaretli).

#### M5-C3 — iOS driver (`packages/body/drivers/ios/`)

**Karar:** **Simulator-first M5**. Real device M6+ ($99/yıl Apple Developer Program enrollment).

**Stack (Ajan 15 + Ajan 10 sentez):**
- **iOS Simulator yolu (M5 default):**
  - **Action layer:** mobile-mcp (Apache 2.0) → Appium XCUITest Driver (Apache 2.0) → WebDriverAgent (BSD).
  - **Vision/screenshot:** `xcrun simctl io booted screenshot`.
  - **Biometric:** `xcrun simctl ui booted biometric_match enrolled` (TouchID/FaceID otomasyon — sadece simulator'da mümkün).
  - 0 ek maliyet, signing yok, 7 gün profile yok.
- **Real device yolu (M6+):**
  - go-ios (MIT) tunnel + WebDriverAgent.
  - Apple Developer Program ($99/yıl) — distribution cert + UDID-tied provisioning.
  - pymobiledevice3 GPL-3.0 ⚠️ — SelfFork core embed YASAK; sadece subprocess çağrı (mobile-mcp zaten go-ios tercih ediyor — temiz çıkış).
  - Biometric otomasyonu real device'da yok; LAContext mock kabul edilebilir (test mode app).

**Reddedilenler (Ajan 15):**
- tidevice (alibaba) — iOS 17 broken, abandoned.
- facebook/idb — 12 ay release yok, inactive.
- BrowserStack/TestMu — proprietary cloud, SelfFork local-first felsefesine ters; vision pipeline latency elverişsiz.

**Action surface:** AndroidDriver ile simetrik (tap/swipe/type/launch_app/screenshot/dump_a11y_tree); ek olarak `simulate_biometric()` simulator-only.

**Audit emit:** `body.driver.start{driver: "ios", runtime: "sim"|"physical", device_id, ios_version}` + standart action events.

#### M5-C4 — macOS desktop driver (`packages/body/drivers/desktop/macos/`)

**Karar:** Native AX-tree primary + screenshot fallback hibrit (Ajan 4 öneri — 10x latency avantajı vs screenshot-only).

**Stack:**
- **Primary:** macOS Accessibility API via PyObjC (yerli `ApplicationServices` framework). atomacos GPL-2.0 ⚠️ **kullanılmıyor** (Apache contamination); doğrudan PyObjC + `AXUIElement` çağrıları.
- **Vision fallback:** `screencapture -x -t png -R<rect>` subprocess + Gemma 4 vision call.
- **Process control:** Apple system AppleScript/JXA ek olarak (`osascript -l JavaScript`).
- **Hammerspoon (MIT, Lua):** desktop window/space management — opsiyonel, M5 default değil.

**TCC permission gating:**
- macOS Accessibility + Screen Recording prompt'ları daemon ilk başlattığında gerekir.
- Daemon installer post-install script: TCC reset + manual approval guide.
- CVE-2025-31250 farkındalığı: TCC trust güvenilirliği sorgulanır oldu — kötüye kullanım denetim audit log'a düşer.

**Action surface:**
```
class MacOSDesktopDriver:
    async def click(x: int, y: int, button: Literal["left","right"] = "left")
    async def double_click(x: int, y: int)
    async def type_text(text: str)
    async def press_key(key_combo: str)  # "cmd+t", "ctrl+a"
    async def scroll(x: int, y: int, dx: int, dy: int)
    async def app_launch(bundle_id: str)
    async def app_activate(bundle_id: str)
    async def screenshot(rect: tuple[int,int,int,int] | None = None) -> bytes
    async def ax_tree(bundle_id: str | None = None) -> dict  # primary path
    async def applescript(script: str) -> str  # T2 warden gate
```

**Reddedilenler (Ajan 4):**
- pyautogui (image-only, DPI/theme/scaling fragility, BSD-3 ama kalite düşük).
- nut.js (Apache OSS ama prebuilts paid + Wayland yok + last stable v4.2.0 / 2024-04 — M5 standardına uymaz).
- SikuliX (vision-only, JVM dependency, M5 native AX hedefiyle çelişir).

**clippy (`examples_crucial/felixrieseberg/clippy`) building block kullanımı (Ajan 11 öneri):**
- **Doğrudan alınır:** `forge.config.ts:300-360` `getNodeLlamaBinaryDependenciesToKeep()` platform/arch matrix; `forge.config.ts:501-555` `forceInstallNodeLlamaBinaries()` cpu-flag bypass; `src/main/main.ts:27-36` `loadLlm()` minimal pattern; `src/ipc-messages.ts:1-46` IPC iskeleti; `src/main/models.ts:266-314` `addModelFromFile()` GGUF import UX.
- **Adapt:** Vision pipeline (clippy'de yok — bizim eklememiz gerek), Electron `utilityProcess`/`Worker` ile llama.cpp izole etme (clippy main-process'te yüklüyor — uzun-soluklu loop UI bloklar), tool-calling protocol (Yamaç Jr `<selffork-tool-call>` blocks — sıfırdan eklenir).
- **Çıkar:** "Clippy karakter" pencere yükü (50+ animation PNG), telemetry, vendor coupling.
- **`@electron/llm@1.1.1` multimodal verify gerek** — `LanguageModelCreateOptions`'a image content desteği henüz teyit edilmedi (Ajan 11 not). M5 implementation öncesi upstream check.

#### M5-C5 — Linux + Windows desktop drivers (M5 sonu opsiyonel veya M6)

ROADMAP §7 ve Ajan 4 ışığında: **M5 default scope DIŞINDA**. M5 sonu son haftada minimum demo (`xdotool` X11 + AT-SPI2 + ydotool Wayland; Windows pywinauto UIA + mss screenshot) opsiyonel. Esas implementation M6 Polish milestone'unda.

---

### M5-D — Sandbox + Permission Warden + Audit Extension

#### M5-D1 — Sandbox tier (OS-level isolation)

**Karar (Ajan 6 öneri):** Çok-katmanlı:
- **macOS dev:** `sandbox-exec` (SBPL profile) — `michaelneale/agent-seatbelt-sandbox` referans; `(version 1) (deny default) (allow file-read-data ... )`.
- **Linux/CI:** bubblewrap + socat proxy egress allowlist (Anthropic Claude Code paterni).
- **Cloud body (rented GPU server):** gVisor (Modal), Firecracker microVM (E2B) opsiyonel — M5'te değil, M6 production deploy'da.

**Mevcut `selffork_orchestrator.sandbox`** subprocess + Docker dual-mode ile (`sandbox/factory.py:14-26`) ABC kontratı (`sandbox/base.py:21-118`) korunur; Body için **yeni katman** `packages/body/sandbox/` action-level warden olarak inecek (orchestrator-side env-isolation'dan ayrı concern; CLAUDE.md MANDATE 7 pillar boundary).

**Yeni implementation'lar:**
- `selffork_orchestrator.sandbox.seatbelt_sandbox.py` — macOS SBPL profile generator + sandbox-exec wrapper.
- `selffork_orchestrator.sandbox.bubblewrap_sandbox.py` — Linux bubblewrap + proxy-egress.
- `selffork_orchestrator.sandbox.factory.py` — `_BACKENDS` dict'e `"seatbelt"` ve `"bubblewrap"` ekle.

#### M5-D2 — Permission Warden (action-level)

**Paket:** `packages/body/sandbox/`

**State machine (Ajan 6 + Codex pattern):**
```
INACTIVE → ARMED → AWAITING_APPROVAL → APPROVED → EXECUTING → AUDITED → ARMED
                          ↓                            ↓
                       DENIED ─────────────────→ AUDITED
                          ↑
                       KILLED (SIGKILL, herhangi state'ten)
```

**3 mod (Codex pattern adapt):**

| Mod | FS | Network | Body action |
|---|---|---|---|
| `read_only` | read all, write none | none | screenshot/scroll/read_text only — TIER0/1 |
| `workspace_write` | RW: project/sessions; deny: ~/.ssh, ~/.aws, ~/Library/Cookies, .env | proxy allowlist | T0+T1 + click/type within allowed domains |
| `danger_full_access` | unrestricted | unrestricted | tüm action — operator `--yolo` benzeri açık onay |

**4-tier risk taxonomy:**

| Tier | Anlam | Action örnekleri | Approval gate |
|---|---|---|---|
| **T0** | Read-only, idempotent | screenshot, scroll, read_dom, ax_tree, list_processes | otomatik (logla, approval yok) |
| **T1** | Local mutation, geri alınabilir | click, type, key_press, navigate (allowlisted), workspace file write | auto-allow mode'da geç, on-request'te onay |
| **T2** | Yan etki yüksek | shell_exec, file_write outside workspace, new domain navigate, app_launch, install_apk, evaluate(js), applescript | her zaman onay (idle timeout = deny) |
| **T3** | Maliyet/hesap riski | payment_form_submit, credential_input, account_login, network_egress_to_unknown_host | her zaman onay + ayrı kanal (Telegram bridge) — 2-key onay |

**Default timeout:**
- AWAITING_APPROVAL: 30 sn (default deny on timeout).
- EXECUTING max-duration cap: per-action 10 sn (override `selffork.yaml`).
- Session idle-timeout: 120 sn (no action → auto-stop).

**Domain comparison (browser-use CVE-2025-47241 dersi):**
- `urlparse` netloc'tan `@` öncesi userinfo strip + port strip + lowercase + IDN punycode normalize.
- Pre-flight check + post-redirect check + new-tab check (browser-use `security_watchdog` pattern).
- Allowlist proxy katmanında (TLS terminate ETMİYOR — Anthropic explicit; data exfil farkındalığı — TLS-MitM proxy M6+ scope).

**Kill switch:**
- Container/process layer: AgentGuard pattern — body process'i ayrı process group, kill switch SIGKILL container'a (agent'a değil).
- Watchdog: orchestrator'da `BodyWatchdog` (max-duration + idle-timeout); aşıldığında otomatik SIGKILL + `body.action.failed` audit `warden_decision="killed"`.
- Operator hook: Cockpit "Stop" butonu + `Ctrl+C` global shell hook + Telegram bridge `/stop` komutu.
- Saga rollback (M5 minimum): T2/T3 form submit Esc+back; gerçek payment rollback M6+.

#### M5-D3 — Audit Category extension

Mevcut 28-kategori (`packages/shared/src/selffork_shared/audit.py:28-57`) Literal closed-set; Body için **5-7 yeni kategori additive eklenir** (geriye uyumlu, eski reader'lar yeni event'leri default `agent.event` legacy'ye fallback ediyordu — bunu kapatıp explicit kategori).

**Yeni AuditCategory entries:**
```
"body.driver.start"        # T0 — driver session açıldı
"body.driver.stop"         # T0 — driver session kapandı
"body.action.invoke"       # T0 — action talep edildi (warden henüz karar vermedi)
"body.action.executed"     # T1/T2/T3 — driver çalıştırdı
"body.action.failed"       # T0 — exception/timeout/kill
"body.permission.requested" # T0 — warden onay bekliyor
"body.permission.deny"     # T0 — warden reddetti / operator denied
"body.vision.query"        # T0 — Gemma 4 vision call
"body.observation"         # T0 — screenshot/AX-tree snapshot (path, binary değil)
```

**Yeni payload alanları (opsiyonel, geriye uyumlu):**
- `risk_tier: T0|T1|T2|T3`
- `action_type: str` (click/type/swipe/...)
- `target_uri_redacted: str` (mevcut redaction pipeline'dan geçer)
- `before_screenshot_ref: str` (path, binary değil)
- `after_screenshot_ref: str`
- `duration_ms: int`
- `warden_decision: Literal["allow","deny","approved","killed"]`
- `warden_reason: str`

**Screenshot persistence path:**
- `~/.selffork/projects/<slug>/screenshots/<session_id>/<ts>_<sha>.png` (orphan: `~/.selffork/screenshots/orphan/<session_id>/...`).
- JSONL'a binary YAZILMAZ — sadece path + sha256 hash.
- Disk rotation: 30 gün retention (configurable `selffork.yaml`); `body.observation` event'i hash referansı tutar, dosya silinince audit replay degrade eder ama integrity hash chain bozulmaz.

**Secret redaction extension:**
- `_SECRET_KEY_PATTERNS` (mevcut 24-entry — ADR-004 close-out'ta `cookie/client_id/signature/pin/otp/nonce/csrf/xsrf/x-api-key` dahil) korunur.
- Yeni eklenir: `screenshot_b64`, `image_b64`, `image_url`, `after_screenshot_b64`, `before_screenshot_b64` — content truncation pattern (`<redacted_image:N_bytes>`).
- `_redact_recursive` 16-depth cap binary string için yetersiz: yeni `_redact_image_payload(value: bytes | str) -> str` katmanı — base64 detect + truncate.
- **OCR-redaction (image içindeki yazı PII'ı): M5 değil, M6'a iter** — banking/auth ekranları için "deny: hassas bölge listesi" with operator opt-in görünür mode başlangıç noktası, OCR-bbox redaction sonraki milestone (Ajan 6 öneri).

**Hash chain (opsiyonel, M6 SOC2 hedefi için):**
- T2/T3 events: `prev_hash + canonical_json → SHA256` event_hash; tamper-evidence.
- T0/T1: opsiyonel, performans-bilinçli.

---

### M5-E — Provider Auth UI (cockpit 5. tab)

**Amaç:** Memory `project_provider_auth_ui_plan.md` (2026-05-09) — Body pillar'ın ilk anlamlı kullanım vakası: "Sign in with browser" — web driver OAuth flow'unu otomatize ediyor. Cockpit 5. tab "Providers" — read-only auth status + browser-driven login orchestration.

**Auth-only kuralı (Yamaç direktifi pekiştirildi):**
- API key ASLA. Sadece subscription OAuth.
- Claude Pro/Max → claude CLI (Ajan 5: **otomasyon kırmızı çizgi** — SelfFork sadece resmi `claude` binary'sini foreground'da süren bir orchestrator olabilir, OAuth token'a kendi dokunmamalı; ToS riski).
- ChatGPT Plus → codex CLI (RFC 8628 device-code; headless temiz; UI showcase).
- Google Code Assist → gemini CLI (browser-callback default + Docker fix PR #3532; `~/.gemini/oauth_creds.json`).
- Z.AI Coding Plan → opencode auth login (API key paste form).
- Minimax sub → mmx CLI (kolay yol — API key paste).

**Cockpit "Providers" tab (yeni route `/cockpit/providers`):**

UI sözleşmesi:
- Provider list: name, status (connected/disconnected/expired/expiring_soon), last_login, expires_at.
- Per-provider actions:
  - "Sign in with browser" → Body web driver OAuth orchestration başlatıyor (browser-use/Stagehand storage_state'e kaydediyor).
  - "Refresh token" — provider-specific (codex device-code re-issue, gemini re-auth, vb.).
  - "Disconnect" — token revoke + storage_state silme.
  - "View audit trail" — son 50 `provider.auth.*` event.

**Browser orchestrator pattern:**
- Order 1: cockpit "Sign in with X" → `body.web_driver.start` → headless=False (operator confirmation), `goto(provider_oauth_url)`.
- Order 2: vision/DOM tracking ile auth flow takip — operator manuel tıklama (M5 Phase 1) ya da Body otomatik form-fill (M5 Phase 2, sadece self-account, TOTP/CAPTCHA bypass YOK).
- Order 3: callback intercept — localhost redirect server (per provider, port allocation 60000-60099 range).
- Order 4: `storage_state` kaydet → `~/.selffork/projects/<slug>/auth/<provider>.json`.
- Order 5: audit emit `provider.auth.success{provider, expires_at}`.

**Yeni AuditCategory:**
```
"provider.auth.requested"    # T0 — auth flow başlatıldı
"provider.auth.success"      # T0 — OAuth callback alındı
"provider.auth.failed"       # T0 — flow hata aldı
"provider.token.refreshed"   # T0 — proactive refresh
"provider.token.expired"     # T0 — runtime detection
```

**Legal/ethics ayrımı (Ajan 5):**
- Operator'ın kendi hesabı için otomasyon ≠ third-party hesabı (KIRMIZI ÇİZGİ).
- TOTP/2FA bypass YASAK — operator manuel sağlar.
- CAPTCHA bypass YASAK — manual intervention prompt.
- ToS-friendly providers (Codex device-code, Gemini, Z.AI, Minimax) **Phase 1 default**; Claude Pro automation **opt-in only** + ToS warning banner.

---

### M5-F — Cockpit extensions

**Yeni route'lar:**
- `/cockpit/fleet` — daemon list + status (M5-A).
- `/cockpit/providers` — Provider Auth UI (M5-E).
- `/cockpit/body` — Body action stream (audit log live tail filtered to `body.*` categories) + screenshot timeline + driver state.

**Yeni Zustand slices:**
- `useFleetStore` — daemon list + heartbeat state + location-aware slider.
- `useProvidersStore` — provider auth status + token expiries.
- `useBodyStore` — driver state + action stream + screenshot history (last 20).

**WebSocket protocol extension (M-1 protokol M4'te kuruldu):**
- Yeni envelope kind'lar: `fleet_status`, `body_action`, `body_observation`, `provider_auth_status`.
- ReplayRegistry process-level buffer Body event'leri için extend.

**Mevcut tab'lara dokunmuyor:** Mission/Run/Chat/Context tab'ları M4'te kapatıldı; M5 sadece **ekleme**, modifikasyon yok (CLAUDE.md surgical disiplin).

---

### M5-G — Tools registry extension

`packages/orchestrator/src/selffork_orchestrator/tools/body.py` (yeni dosya):

```python
@toolspec
class BodyClickArgs(ToolArgs):
    target: str  # selector or label
    bbox: tuple[int,int,int,int] | None = None
    button: Literal["left","right"] = "left"

@toolspec
class BodyTypeArgs(ToolArgs):
    text: str
    target: str | None = None  # active focus if None

@toolspec
class BodyScreenshotArgs(ToolArgs):
    rect: tuple[int,int,int,int] | None = None

# ... 8-10 body.* tools
```

`tools/__init__.py:32-39` `build_default_registry`:
```python
ToolRegistry(specs=[
    *build_kanban_tools(),
    *build_mind_tools(),
    *build_quota_tools(),
    *build_session_tools(),
    *build_autopilot_tools(),
    *build_body_tools(),  # YENI
])
```

`ToolContext` (`tools/base.py:55-96`) extension — `body_driver: object | None = None` (BodyDriver protocol) field'ı eklenir; mevcut tüm tool'lar None'a düşer (geriye uyumlu).

**Naming kuralı:** snake_case, body-prefix. `body_click`, `body_screenshot`, `body_type`, `body_scroll`, `body_swipe`, `body_app_launch`, `body_press_key`, `body_storage_state_save`, `body_storage_state_load`, `body_ax_tree`. Pattern jr_tool_protocol underscore-flat (kanban_card_*, mind_recall) ile uyumlu.

---

## Eski karar (revize)

**`docs/ROADMAP.md` §7 "Driver Roadmap (Body)"** (lines 966-974) — vision driver tier kısıtı **revize edildi**:

| Driver | Önceki Tier | Yeni Tier | Yeni Earliest |
|---|---|---|---|
| `desktop/` (CLI control via tmux) | Nano | Nano | M5 (değişmedi) |
| `web/` (browser-use/skyvern reference) | Full Vision (post-v2.0) | **Nano + E2B vision** | **M5** |
| `android/` (mobile-mcp + docker-android) | Full Vision (post-v2.0) | **Nano + E2B vision** | **M5** |
| `ios/` (appium-mcp) | Full Vision (post-v2.0) | **Nano + E2B vision (sim only)** | **M5** (real device M6+) |
| `desktop-vision/` (OS click + type) | Full Vision (post-v2.0) | **Nano + E2B vision (macOS only)** | **M5** (Linux/Windows M6+) |

**Gerekçe:** Ajan 7 (vision prompting research) Gemma 4 E2B native pointing + JSON bbox capability'sini doğruladı (HF blog gemma4 + ai.google.dev/gemma/docs/capabilities/vision); Ajan 8 (browser-use deep) Ollama + Gemma 4 entegrasyon path'inin hazır olduğunu gösterdi. "26B A4B Full Vision tier" gereksinimi conservative tahmindi — E2B yetebilir (Q4_0'da head-to-head eval M5 implementation'da yapılacak; başarısız olursa M5 sonu karar — Bouncing Back Path: vision drivers'ı M6'a geri al, daemon scope'u M5 olarak finalize).

**`docs/ROADMAP.md` §M5 "Body Daemon" (line 576)** scope **genişletildi** — daemon (mevcut scope) + vision drivers (yeni). 3-4 hafta tahmini → 6-8 hafta. ROADMAP §0 ve §3 critical path tabloları M5 close-out'unda revize edilecek.

---

## Etki

### Pillar 1 (Reflex)
- M7 fine-tune SFT dataset hazırlığı için body action audit JSONL doğrudan tüketilebilir (`body.action.executed` → (state_t, action_t) pair → Yamaç-only weighted loss training).
- ChatMessage multimodal migration → reflex eğitim formatına uygun screenshot+text pair zaten doğal akış.
- M5 implementation'ında held-out user session corpus ilk freeze (Ajan 13 öneri — `benchmarks/yamac_session_holdouts/` placeholder, M6'da dolduruluyor).

### Pillar 2 (Body)
- packages/body/ skeleton (ADR-001 §4 + §14.9 — 9 boş `__init__.py`) M5'te dolacak: `body/daemon/`, `body/drivers/{desktop,web,android,ios}/`, `body/sandbox/`, `body/vision/`.
- Cross-pillar boundary korunuyor (CLAUDE.md MANDATE 7); orchestrator-side `selffork_orchestrator.sandbox` (env-isolation) ve body-side `selffork_body.sandbox` (action-level warden) **ayrı concern**.

### Pillar 3 (Mind)
- Body event'leri Mind T1 short-term memory'ye episodic event olarak akar (mevcut `mind.note.write` audit category zaten var; `body.action.executed` kategori ile genişletme — `mind_router` Body event'leri otomatik consume edebilir).
- Vision capture metadata (screenshot path, action target) Mind T2 episodic memory için yeni input source — sentinel detection ile otomatik ingest.
- T3 Semantic Graph: `body.driver.<X>` events → graph node'ları (driver session, target page, action sequence).

### Cockpit (M4 üstüne ekleme)
- Yeni 3 route (Fleet, Providers, Body) + 3 yeni Zustand slice + 4 yeni WebSocket envelope kind.
- Mevcut Mission/Run/Chat/Context tab'ları **dokunulmuyor** (M4 kapandı, surgical).
- M-1 WS protocol + ReplayRegistry process-level buffer Body event'leri için additive.

### Cross-cutting infra
- `LLMRuntime.invoke` text-only → multimodal extension (B2 blocker, ADR-005 prereq).
- `AuditCategory` Literal extension (B3 blocker, 9 yeni entry).
- `_SECRET_KEY_PATTERNS` screenshot/image redaction extension (B4 blocker, 5 yeni pattern + `_redact_image_payload` katman).
- `ToolContext` extension (`body_driver: object | None`) — geriye uyumlu, breaking değil.

---

## Kabul kriterleri (M5 done)

### Daemon Layer (M5-A)
- [ ] Daemon round-trip Tailscale üzerinde **p95 < 2sn** (prompt → execute → result).
- [ ] Daemon graceful reconnect ≤ 60sn (network drop sonrası).
- [ ] Daemon startup ≤ 5sn; idle CPU ≤ %5; idle RAM ≤ 100MB.
- [ ] macOS arm64+amd64 + Windows x64 + Ubuntu x64+arm64 binary'leri çalışıyor; installer'lar (Homebrew tap, .msi, .deb) end-to-end.
- [ ] Cockpit Fleet view: 3 daemon list + heartbeat + latency_ms canlı.
- [ ] Location-aware slider auto-shift (home=7 ↔ work=4).
- [ ] Demo: home Mac → work Ubuntu daemon → CLI lane spawn → result home cockpit'te.

### Vision Pipeline (M5-B)
- [ ] `MultimodalLLMRuntime.invoke_with_images()` MLX server backend'inde çalışıyor.
- [ ] ChatMessage migration tamamlandı; 4 CLIAgent + tools layer regression-free.
- [ ] End-to-end screenshot→action **p95 < 2sn** (decode token ≤ 50, default 280 token budget).
- [ ] Locate-by-label JSON output reliability ≥ %85 (held-out 30-task corpus).
- [ ] Tier-1 → Tier-2 → Tier-3 fallback chain manual smoke + 3 senaryo geçti.

### Drivers (M5-C)
- [ ] Web driver: 5 senaryo (Google search, GitHub PR review, calendar event, OAuth login, form submit) **manual smoke geçti**; storage_state per-provider çalışıyor.
- [ ] Android driver: 3 senaryo (Settings → Wi-Fi toggle, Chrome → URL nav, app install via APK) docker-android container'da geçti.
- [ ] iOS driver: 3 senaryo (Safari nav, Settings → biometric enroll trigger, Mail send) iOS Simulator'da geçti.
- [ ] macOS desktop driver: 3 senaryo (Finder file ops, Terminal command, Browser nav) AX-tree primary + screenshot fallback ikisi de canlı.
- [ ] Tmux desktop driver (M3 reuse): 5 CLI canlı (claude/codex/gemini/opencode/mmx) — M3 kapsamından regression yok.

### Sandbox + Permission Warden + Audit (M5-D)
- [ ] `selffork_body.sandbox.PermissionWarden` 3-mod state machine geçti (read_only / workspace_write / danger_full_access).
- [ ] T0/T1/T2/T3 risk taxonomy 9 yeni body.* + 5 yeni provider.* AuditCategory ile JSONL emit.
- [ ] Screenshot persistence path pattern (`~/.selffork/projects/<slug>/screenshots/...`) çalışıyor; binary inline yazılmıyor.
- [ ] `_redact_image_payload` katmanı + `_SECRET_KEY_PATTERNS` extension: hiçbir audit log satırında raw screenshot bytes veya OAuth token leak YOK.
- [ ] BodyWatchdog kill-switch: max-duration cap + idle-timeout + Cockpit "Stop" + Telegram `/stop` üçü de canlı; SIGKILL container'a (agent'a değil) gidiyor.
- [ ] Domain comparison `urlparse` userinfo strip + port strip + IDN normalize — CVE-2025-47241 paterni geçiyor.
- [ ] macOS sandbox-exec profile + Linux bubblewrap profile dev-mode'da çalışıyor; cloud gVisor M6+'a iter.

### Provider Auth UI (M5-E)
- [ ] Cockpit "Providers" tab read-only status surface canlı (5 provider).
- [ ] "Sign in with browser" 3 senaryo (codex device-code + gemini browser-callback + opencode form paste) end-to-end geçti.
- [ ] storage_state per provider `~/.selffork/projects/<slug>/auth/<provider>.json` kaydediliyor.
- [ ] 5 yeni `provider.*` AuditCategory event JSONL'a düşüyor.
- [ ] ToS warning banner Claude Pro otomasyonu opt-in flow'unda görünüyor; default disabled.

### Test + Lint
- [ ] Backend test: M4 baseline (1248) üstünde + Body pillar testleri ≥ 1500 toplam.
- [ ] Frontend test: M4 baseline (83) üstünde + Cockpit Body/Fleet/Providers testleri ≥ 130 toplam.
- [ ] Daemon test (Go): unit ≥ %80 coverage + 1 e2e (mocked Tailscale) round-trip.
- [ ] `ruff` Body pillar dosyaları clean; mevcut S108 7 baseline tech debt M5'te kapatılır (ADR-004 §Sınırlamalar 9 madde).
- [ ] `mypy --strict` Body pillar dosyaları (Python kısmı) success.
- [ ] Manuel smoke checklist (operator laptop): tüm 4 driver + Fleet view + Provider Auth UI + sandbox kill-switch.

### Audit-fix wave (M5 close-out)
- [ ] 9 paralel audit-god ajanı (M4'tekiyle aynı disiplin).
- [ ] P0/HIGH bulgular kapatılmadan M5 close edilmez.

### Documentation
- [ ] `docs/architecture/body-daemon-protocol.md`
- [ ] `docs/architecture/body-vision-pipeline.md`
- [ ] `docs/architecture/body-permission-warden.md`
- [ ] `docs/operations/install-daemon-{macos,windows,ubuntu}.md`
- [ ] `docs/operations/provider-auth-ui-guide.md`
- [ ] `docs/research/M5_korpus.md` — 16 ajan ARGE özetinden korpus dosyası.
- [ ] ADR-005 close-out (Sınırlamalar/kalan iş + Audit-fix wave bölümleri M5 close'da dolduruluyor).

---

## Sınırlamalar / kalan iş (M6/M7'ye iter — confirmed)

M5 scope DIŞINDA, ileride alınacak (15 madde — ADR-004 §Sınırlamalar 9 maddesi + 6 yeni M5-derived):

### M5'te kapatılan ADR-004 borçları
1. **S108 test path tech debt** — 11 dosyada 35 occurrence, M5 sırasında `tmp_path` fixture rewrite (ADR-004 §Sınırlamalar 9 madde).

### M6 Polish'a iter
2. **iOS real device support** — $99/yıl Apple Developer Program enrollment + go-ios tunnel + WDA build sign + UDID provisioning.
3. **Linux + Windows desktop drivers** — xdotool + AT-SPI2 (Linux) + pywinauto + mss (Windows). M5 sonu opsiyonel demo kabul edilir.
4. **Skyvern AGPL boundary enforcement** — `examples_crucial/skyvern/` `.gitignore` veya pre-commit hook ile import yasağı (AI agent kazara kopya riski).
5. **Token-level chat streaming** — şu an message-level; round-loop driver hook M5+'a iter (ADR-004).
6. **Drag-drop kanban** — read-mostly contract M5'te değişmiyor (ADR-004).
7. **Replay-on-reconnect REST fallback** — WS replay buffer çalışıyor; REST fallback opsiyonel (ADR-004).
8. **OpenAPI type-sync CI hook** — manuel `pnpm gen:api` yeterli M5'te (ADR-004).
9. **mind_deps refactor** — `cli_mind.py` ↔ `mind_deps.py` duplikasyonu, P2 (ADR-004).
10. **Mind T2 alt-path dedicated test** — implementation var, test eksik (ADR-004).
11. **T3 Semantic Graph force-graph viz** — Context tab placeholder yeterli (ADR-004).
12. **ProvenanceFeed component** — orphan API export `openMindProvenanceStream` UI'ya bağlı değil (ADR-004).

### M7 Reflex'e iter
13. **Yamaç-stili held-out corpus + custom eval** — M5 implementation sırasında ilk freeze, M6'da büyütme; SFT dataset'le birebir uyumlu (Ajan 13 öneri).
14. **OCR-bbox redaction (image içindeki PII)** — M5'te "deny: hassas alan listesi" + operator opt-in görünür mode başlangıç noktası; OCR-redaction M6+ (Ajan 6).

### Post-v2.0
15. **Stealth/CAPTCHA bypass automation** — Camoufox/nodriver/Patchright + 2FA TOTP otomasyonu. **Legality gate** — Yamaç scope kararı + ToS-friendly self-account constraint (Ajan 16).
16. **Scraping katmanı** — Crawl4AI/Firecrawl/trafilatura + ScrapeGraph-AI. Mind pillar'ın "external knowledge ingest" iş kalemi, M6 `mind/ingest/` altında (Ajan 16).
17. **Cloud body sandbox** — gVisor (Modal) / Firecracker microVM (E2B) rented GPU server üzerinde paralel agent isolation. macOS dev'de seatbelt yeterli, M5 implementation'ında.
18. **mmx + opencode E2E** — subscription yenilenince (Yamaç pending; ADR-004).
19. **TLS-MitM proxy (operator-installed CA)** — egress allowlist için domain-fronting koruması; M5'te allowlist dar tutarak risk azaltıyoruz, MitM M6+ scope.
20. **Hash chain SOC2 audit trail** — T0/T1 events için opsiyonel `prev_hash + canonical_json → SHA256`. T2/T3 M5'te opsiyonel olarak başlanabilir; full SOC2 hedefi M6+.

---

## Risk register (M5 scope)

| # | Risk | Olasılık | Etki | Mitigation |
|---|---|---|---|---|
| R1 | Gemma 4 E2B Q4_0 vision native pointing güvenilirliği yetersiz çıkar (held-out eval başarısızlığı) | M | H | Bouncing Back Path: vision drivers'ı M6'a geri al, M5 = daemon-only finalize. ROADMAP §0 + §3 revize. |
| R2 | Tailscale latency work network'te sürekli > 80ms (ROADMAP M5 risk) | L | M | Cockpit'te latency surface; orchestrator 20-80ms baseline tolere; operator escalates if work network blocks Tailscale. |
| R3 | Cross-platform daemon packaging zorluğu (Apple notarize + Windows Authenticode + Linux .deb sign) | M | H | Go binary preferred (single static); detailed install-daemon-*.md doc per platform. M5 slip > 6 hafta ise Bouncing Back: ship macOS daemon only at v1.0; Win+Ubuntu v1.1. |
| R4 | Stagehand vendor-lock (Browserbase olmadan tamamen lokal Playwright + lokal LLM çalışır mı) | M | M | M5 implementation öncesi `selffork-researcher` + lokal kod doğrulaması. Başarısızsa Stagehand'i opsiyonel layer olarak iter et, Playwright + custom DOM extraction primary. |
| R5 | iOS real device feasibility post-M5 | L | L | M5 sim-only; M6+'da Apple Developer enrollment kararı operator'a bağlı; sim coverage M5 demo için yeterli. |
| R6 | macOS TCC permission UX'i daemon'a göre yetersiz (CVE-2025-31250 farkındalığı) | M | M | Detailed TCC reset+approval guide; daemon installer post-install script; manual approval prompt rate. |
| R7 | Browser CVE-2025-47241 benzeri domain bypass exploit'i SecurityWatchdog'da kaçar | L | H | `urlparse` userinfo+port+IDN normalize testleri; OWASP/security-research feed monitoring; M5 close-out audit-god review. |
| R8 | Permission warden 3-mod konfigürasyon UX kafa karıştırıcı | M | M | Cockpit Body tab'da mod seçici + tooltip + per-action gerekçe; smoke test 5 senaryo (3 mod x 4 driver). |
| R9 | Screenshot disk usage patlaması (30 gün retention × yüksek frequency body) | M | M | Configurable retention `selffork.yaml`; auto-cleanup daemon; cockpit'te disk usage gauge; default 7 gün retention konservatif başlangıç (operator override). |
| R10 | ChatMessage migration regression (4 CLIAgent + tools layer) | L | M | Migration ayrı PR (M5 öncesi); regression test: M3+M4 1331 test pass + manual smoke. |

**ROADMAP M5'in mevcut Risks (lines 632-640) korunuyor:**
- Tailscale latency variability → R2.
- Cross-platform daemon packaging → R3.
- Windows tmux WSL2 zorluğu → mitigation: PowerShell job control fallback.

---

## Referanslar

### ADR-005 ARGE — 16 paralel ajan raporu (2026-05-10)

**10 selffork-researcher (dış araştırma):**
- Ajan 1 — Vision-action loop architecture rivals (Anthropic CU + OpenAI Operator + browser-use + Skyvern + mobile-use + LaVague + E2B desktop + SoM): hibrit DOM+screenshot baskın; Skyvern AGPL kırmızı çizgi; benchmark snapshot Ekim 2025 OSAgent 76.26% / browser-use 89% WebVoyager.
- Ajan 2 — Mobile Android landscape (docker-android + mobile-mcp + uiautomator2 üçlüsü; Detox/Maestro/Frida/Genymotion reddedilenler; license filter Apache/MIT öncelik).
- Ajan 3 — Web driver vision-first vs DOM-first (DOM-first 12-17pt avantaj; Playwright storage_state auth standardı; CAPTCHA/anti-bot M6+ scope).
- Ajan 4 — Desktop driver cross-platform (macOS AX 10x screenshot-only; clippy building block; nut.js paid + Wayland yok; atomacos GPL-2.0 ⚠️).
- Ajan 5 — Provider Auth UI OAuth flows (Claude Pro automation kırmızı çizgi; Codex device-code temiz; Gemini browser-callback + Docker fix; Z.AI/Minimax API key paste).
- Ajan 6 — Sandbox + permission warden (4-tier: OS sandbox + proxy egress + warden + audit JSONL; Anthropic %84 prompt azalması; T0/T1/T2/T3 risk_tier; AgentGuard SIGKILL container).
- Ajan 7 — Vision prompting Gemma 4 (native pointing + bbox JSON; token budget 280 default; locate-by-label primary; SoM Q4_0'da test edilmemiş; latency 1-2sn üst sınıra yakın).
- Ajan 13 — Computer-use benchmarks (WebArena Verified + OSWorld-Verified + AndroidWorld + ScreenSpot-Pro + OS-Harm 5-pillar; 5 metric: action precision + e2e TSR + step efficiency + safety violation rate + latency p50/p95).
- Ajan 15 — iOS feasibility (KOŞULLU YAPILABİLİR; simulator-first M5 OK; real device M6+ $99/yıl; pymobiledevice3 GPL-3.0 ⚠️; tidevice iOS 17 broken; facebook/idb inactive).
- Ajan 16 — Modern web automation + scraping (Stagehand v3 MIT primary candidate; Camoufox/nodriver/Patchright stealth M5 dışı; Crawl4AI/Firecrawl scraping M6 scope).

**5 explorer-god (lokal repo):**
- Ajan 8 — examples_crucial/browser-use deep (CDP-first + DOM tree dual-mode + 14 watchdogs + BaseChatModel Protocol + Ollama integration ready; cloud sandbox + telemetry reddedilen; MIT).
- Ajan 9 — examples_crucial/Skyvern-AI/skyvern deep (AGPL-3.0 KOD KOPYALAMA YASAK; SCRAPE_TYPE_ORDER + failure_classifier + PermissionChecker ABC + ScrapedPage hybrid feed pattern alınır; 25+ block + CodeBlock sandbox + litellm reddedilenler).
- Ajan 10 — examples_crucial/minitap-ai/mobile-use deep (Apache 2.0; LangGraph multi-agent reddedilen — tek-model rol prompt; iOS sim CI working macos-14 + iOS 17.2; real iOS "not yet supported" README:169; minitap proprietary provider reddedilen).
- Ajan 11 — examples_crucial/felixrieseberg/clippy deep (MIT; Electron + @electron/llm + node-llama-cpp + GGUF; earlier Gemma generation listed (NOT Gemma 4) — bizim Gemma 4 hedefimize uyum için clippy adapter override gerekir; vision/screenshot/desktopCapturer SIFIR — bizim eklememiz gerek; forge.config build matrix Metal/CUDA/Vulkan alınır).
- Ajan 12 — packages/body + sandbox + tools state (skeleton ADR-001 §4 + §14.9 hazır; ROADMAP §7 conflict tespit; ChatMessage = dict[str,str] migration; AuditCategory closed Literal extension; mlx_vlm hardcoded mlx_server.py:129; Sandbox ABC subprocess+Docker; permission warden = NEW; ToolContext extension geriye uyumlu).

**1 audit-god:**
- Ajan 14 — Pre-M5 cleanup audit (3 HIGH blocker: permission warden YOK + LLMRuntime text-only + AuditCategory body.* yok; 1 MEDIUM: screenshot redaction; ADR-004 §Sınırlamalar 9 madde tamamı P2 — Body için pre-req değil; 4 entegrasyon noktası: tools/body.py + AuditCategory extend + _SECRET_KEY_PATTERNS extend + LLMRuntime multimodal).

### Önceki ADR'lar
- `docs/decisions/ADR-001_MVP_v0.md` — packages/body skeleton (§4 + §14.9 sandbox/audit mandate).
- `docs/decisions/ADR-002_Mind_Architecture.md` — Mind T1-T6 + GraphRAG (M2'de iniyor).
- `docs/decisions/ADR-003_M3_CLI_Surfing.md` — 6 CLI snapper + Jr autopilot 11-tool + HandoffBundle + PtbTelegramBridge (M3 close-out).
- `docs/decisions/ADR-004_M4_Cockpit.md` — M-1 WS protocol + 4-tab cockpit + audit JSONL 28-category + secret redaction _SECRET_KEY_PATTERNS 24-entry (M4 close-out, §Sınırlamalar 9 madde M5+'a iter).

### Roadmap + Kararlar
- `docs/ROADMAP.md` §0 (overview) + §M-1/M0/M1/M2/M3/M4/M5/M6/M7 (milestones) + §3 (critical path) + §7 (driver roadmap — bu ADR ile revize) + §11 (Nano v1.0) + §12 (Full Vision v2.0).
- `docs/Yamac_Jr_Nano_Kararlar.md` — base model + context window + fine-tune metodolojisi + dataset format + loss strategy SSoT.

### Korpus referansları (MANDATE 9)
- `examples_crucial/browser-use/` — Apache 2.0, web driver primary referans.
- `examples_crucial/Skyvern-AI/skyvern/` — AGPL-3.0, sadece architectural pattern referansı (kod kopyalama YASAK).
- `examples_crucial/minitap-ai/mobile-use/` — Apache 2.0, mobile driver birebir referans.
- `examples_crucial/felixrieseberg/clippy/` — MIT, desktop building block (Electron + llama.cpp + GGUF stack).

### Memory entries (project + feedback)
- `feedback_backend_first.md` — minik functional scope, enterprise quality.
- `feedback_no_mvp_full_quality_first_time.md` — pluggable interfaces day 1.
- `feedback_brand_is_selffork_not_personal_name.md` — fork-friendly, "operator" generic.
- `project_provider_auth_ui_plan.md` — M5+ Body pillar feature (bu ADR'da M5-E olarak inişi).
- `project_per_cli_auto_approve_flags.md` — 5-CLI auto-approve matrix (M3 close-out).
- `project_jr_tool_protocol.md` — `<selffork-tool-call>` wire format (M3'te kuruldu, M5 body.* tool'larıyla genişler).
- `project_done_sentinel_protocol.md` — `[SELFFORK:DONE]` substring session-end protocol (M3'te kuruldu, M5 body driver session lifecycle ile uyumlu).
- `project_m3_cli_surfing_complete.md` — M3 done state (6 snapper + Jr autopilot + HandoffBundle).

### Akademik + dış kaynak
- HF blog gemma4 — Gemma 4 vision capability (native pointing + JSON bbox).
- ai.google.dev/gemma/docs/capabilities/vision — vision-language Gemma 4.
- Datature CV guide — Gemma 4 production patterns.
- Set-of-Marks paper arxiv 2310.11441 (Microsoft Research).
- ScreenSpot-Pro arxiv 2504.07981 (UI grounding benchmark).
- AndroidWorld google-research.github.io (mobile benchmark, Apache 2.0).
- WebArena Verified (Apache 2.0).
- OSWorld-Verified xlang-ai/OSWorld (Apache 2.0).
- OS-Harm arxiv 2506.14866 (safety eval).
- Anthropic Computer Use docs (platform.claude.com).
- OpenAI Codex sandbox docs (developers.openai.com/codex/).
- AgentGuard A386official/agentguard (Docker ephemeral container + 4-tier).
- Microsoft Agent Governance Toolkit (microsoft/agent-governance-toolkit, Apr 2026).
- browser-use docs (docs.browser-use.com).
- mobile-use minitap-ai (github.com/minitap-ai/mobile-use, Apache 2.0).
- Stagehand v3 launch (browserbase blog).
- Skyvern WebVoyager 85.8% blog (skyvern.com).
- Apple Developer Program / WebDriverAgent / xcrun simctl docs.
- CVE-2025-47241 (browser-use security advisory GHSA-x39x-9qw5-ghrf).
- CVE-2025-31250 (macOS TCC trust).

---

## Sınırlamalar / kalan iş — Genişletilmiş (2026-05-15 audit-fix wave + 10 crucial corpus analizi sonrası)

Toplam **41 iter maddesi**. Detaylı liste + path:line kanıtları: `docs/M5_SESSION_HANDOFF.md §2`. Özet kategoriler:

### M5+ patch (deploy sonrası, 1-2 sprint)
- LatencyTracker → VisionOrchestrator wiring (`runtime.py:202-223`)
- audit_emit exception guard (defansif try/except wrap)
- Stagehand v3 vendor-test artefakt (R4 gate)
- SecurityWatchdog.attach() fix (`page.context.event_loop` Playwright public API'de YOK)
- PlaywrightWebDriver.evaluate() warden gate (T2 enforcement)
- provider arg whitelist (BodyStorageStateSaveArgs path traversal)
- AppleScriptRunner JS injection escape (newline/semicolon)
- CGWindowListCreateImage deprecated (macOS 14.4+ ScreenCaptureKit)
- body driver subprocess start_new_session=True (process group SIGKILL alignment)
- AndroidDriver.scroll baseline runtime window_size (hardcoded 1080×1920)
- AppiumXcuitestAdapter device_name vs udid capability mapping
- ScreenshotStore path traversal sanitize (session_id/project_slug regex)

### M6 polish (3-4 hafta)
- command_intake WS dial loop (daemon bidirectional fleet implementation)
- register 409 returns auth_key (rotation impossible şu an)
- HMAC cross-language doc + Python helper (`fmt.Sprintf("%v")` ambiguity)
- Makefile codesign + notarytool target (release pipeline)
- provider_router /refresh worker (stub)
- 30-task held-out vision eval harness (`benchmarks/m5_vision_eval/`) — **cua HUD pattern** kullanılabilir
- bubblewrap egress allowlist + SandboxConfig.egress_policy field
- body_router decide_permission session-scoped lookup (request_id collision)
- TLS-MitM proxy (operator-installed CA)
- Hash chain SOC2 audit trail (T2/T3 events `prev_hash + canonical_json → SHA256`) — **hermes-agent referansı YANLIŞ** (Ajan 9 false-positive, audit-god Ajan 8 doğruladı); alternatif: AWS QLDB / Hyperledger Fabric / RFC 6962 / Sigstore Rekor
- OCR-bbox redaction (image içindeki PII)
- Codebase RAG / Mind ingest — **claude-context tree-sitter + Merkle DAG pattern** (`packages/mind/ingest/codebase/`)
- Mind auto-forget / TTL — **agentmemory `forgetAfter` + contradiction-similarity 0.9 pattern** (`packages/mind/forget/`)
- Cross-platform Linux/Windows desktop driver — **UI-TARS-desktop nut-js operator referans**
- Stealth web automation opsiyonel layer — **CloakBrowser Playwright executable_path swap** (madde 15'i güncelle)
- VM-tier sandbox for cloud body — **cua BaseComputerProvider + Lume/Lumier/WinSandbox pattern**

### M7 Reflex (M5 audit log → SFT dataset köprüsü)
- **EvolutionEvent şeması adopt** (evolver pattern) — `outcome.score`+`signals[]`+`parent_id` M5 audit log'a; Yamaç-only weighted loss filtre kriterleri
- **GenericAgent `_clean_content` pattern** (SFT context shrinking)
- **AGIO telemetry schema** (UI-TARS-desktop) — Cockpit Fleet event reference

### Yeni ADR adayları
- **ADR-006 Skill Packs** — `.selffork/skills/<bucket>/<skill>/SKILL.md` standardı; cross-CLI registry. Referanslar: mattpocock/skills (MIT) + scientific-agent-skills (MIT) + awesome-codex-skills (per-skill MIT). **GPL-3.0** TrendRadar + evolver kod kopyalama YASAK.

### M3+M4 baseline borçları (M5'te kapanmadı)
- S108 test path tech debt (11 dosya × 35 occurrence)
- mind_deps refactor (cli_mind.py duplikasyonu)
- Mind T2 alt-path dedicated test
- Drag-drop kanban
- Replay-on-reconnect REST fallback
- OpenAPI type-sync CI hook
- ProvenanceFeed component orphan UI
- T3 Semantic Graph force-graph viz

---

## Audit-fix wave (2026-05-15 close-out, 9 paralel audit-god ajanı + 10 explorer-god ajanı)

**9 audit-god (M5 close-out):** P0/HIGH bulgular kapatıldı — server.py 3 router mount + WS envelope kind extension + body pyproject.toml deps + ToolContext 5 field + _gate default-deny + _invoke audit emit + ScreenshotStore wiring + storage_state 0o600 + PyObjC tuple robust + tmux multi-line + docker-android emulator serial + AndroidDriver.stop try/finally + provider_router disconnect file delete + PermissionRow try/catch/finally + sidebar nav items + ROADMAP §M5/§7/§3.3 revize + 4 yeni regression test.

**10 explorer-god (5 M5 kritik + 5 pillar ref):** 11 ek crucial repo (UI-TARS-desktop, cua, CloakBrowser, financial-services, video-search-and-summarization, agentmemory, claude-context, Archon, hermes-agent, GenericAgent, evolver) + 5 skill survey (TrendRadar, scientific-agent-skills, mattpocock/skills, andrej-karpathy-skills, awesome-codex-skills) klonlandı ve analiz edildi. M5 deploy bloklayan bulgu YOK; tüm bulgular M5+/M6 iter listesine eklendi.

**Test final:**
- Backend: 1413 pass + 1 skip (Pillow opsiyonel) + 3 M3 baseline errors (test_logging.py fixture)
- Frontend: 97 pass (11 test files)
- Go daemon: command_intake 84.1% ≥%80 ✓; cli_bridge 57%; heartbeat/state_reporter düşük (M5+ iter)
- ruff M5 dosyaları: All checks passed

---

**Onay bekliyor:** operator review. Approval sonrası:
1. ADR-005 status: PROPOSED → ACCEPTED.
2. `docs/plans/M5_Body_Plan.md` 9-order detailed plan hazırlanır (M4 paterniyle 1500+ satır enterprise-grade).
3. audit-god review pass.
4. ROADMAP.md §7 + §M5 + §0/§3 revize PR.
5. Implementation.

**Süre tahmini:** 6-8 hafta.
**Bouncing Back:** R1 tetiklenirse vision drivers M6'a geri al, M5 = daemon-only finalize (3-4 hafta).
