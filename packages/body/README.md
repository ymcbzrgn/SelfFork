# selffork-body

**Status:** Implemented — M5 Body pillar shipped and extended through
S-ToolFleet Faz 0–4 (see [ADR-005](../../docs/decisions/ADR-005_M5_Body.md)
and [ADR-010 §9](../../docs/decisions/ADR-010_Vision_Lock.md)). The
289-tool fleet in `packages/orchestrator/.../tools/` drives this package's
drivers through `BodyDriverProtocol`.

## Sub-packages

| Sub-package | Purpose | State |
|---|---|---|
| `drivers/android/` | ADB / mobile-mcp adapter + uiautomator2 fallback | ✅ implemented + tested |
| `drivers/ios/` | Appium XCUITest adapter + simctl Simulator runtime (real device: NotImplementedError by design — Apple Developer Program required) | ✅ implemented + tested |
| `drivers/web/` | `PlaywrightWebDriver` (~50 methods: navigation, tabs, storage, stealth, network interception, device emulation) | ✅ implemented + tested |
| `drivers/desktop/macos/` | `MacOSDesktopDriver` (click/type/screenshot/clipboard/windows/say) | ✅ implemented + tested |
| `drivers/vr/` | `QuestDriver` (Android-derived, controller/passthrough/Guardian) + `VisionProDriver` (visionOS sim, vision-only) | ✅ implemented + tested |
| `drivers/mobile_factory.py` | `build_default_body_driver()` — env-driven platform resolution (`SELFFORK_BODY_PLATFORM`: ios/android/web/macos/quest/visionpro) + `CompositeMobileDriver` | ✅ implemented + tested |
| `vision/` | Screenshot → decision → action loop (Gemma vision adapter, preprocess, delta-image) | ✅ implemented + tested |
| `sandbox/` | Action-level permission warden, audit, kill-switch | ✅ implemented + tested |
| `storage/` | Screenshot store | ✅ implemented + tested |
| `daemon/` (Go) | Remote-machine daemon: heartbeat, state reporter, tmux CLI bridge (command intake WS + Windows PowerShell bridge still pending) | 🟡 partial |

> **NB:** This package's `sandbox/` is **action-level** (per-tool-call permission gating). The orchestrator-level sandbox (env isolation) lives in `packages/orchestrator/sandbox/`. Different concerns; no shared interface.
