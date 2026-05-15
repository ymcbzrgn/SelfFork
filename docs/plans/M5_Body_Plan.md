# M5 — Body (Cross-Platform Daemon + Vision Drivers + Provider Auth UI): 9-Order Implementation Plan

**Tarih:** 2026-05-10
**Milestone:** M5 — Body
**ADR:** [ADR-005_M5_Body.md](../decisions/ADR-005_M5_Body.md) (ACCEPTED 2026-05-10)
**Süre tahmini:** 6-8 hafta (handoff vision drivers + ROADMAP daemon birleşik scope)
**Bouncing Back:** R1 (Gemma 4 E2B vision yetersiz) tetiklenirse vision drivers M6'a geri al, M5 = daemon-only finalize (3-4 hafta).

---

## 1. Genel bakış

M5 Body pillar üç katmanı tek session'da inşa ediyor:

1. **Daemon Layer** — cross-platform Go binary (macOS/Win/Ubuntu) + Tailscale ACL + Cockpit Fleet view + location-aware slider + tmux desktop CLI driver. Operator'ın home Mac'inden iş Windows + Ubuntu'ya "beyni uzatma".
2. **Vision-Driven UI Drivers** — Gemma 4 E2B multimodal pipeline + 5 driver: web (Playwright+browser-use referans+Stagehand v3 hibrid), Android (docker-android+mobile-mcp+uiautomator2), iOS sim (Appium XCUITest+WDA+go-ios), macOS desktop (AX-tree+screenshot fallback+clippy building block), tmux desktop (M3 reuse).
3. **Sandbox + Permission Warden + Provider Auth UI** — `packages/body/sandbox/` action-level warden (3-mod + 4-tier risk_tier) + 9 yeni `body.*` + 5 yeni `provider.*` AuditCategory + cockpit 5. tab Provider Auth UI ile browser-driven OAuth orchestration.

**Yaklaşım:**

- **MANDATE 1 (git yasağı):** Her Order kapanış'ında "Commit edilmeye hazır. İstersen sen yap." denir; commit/push asla otomatik.
- **MANDATE 5 (ajanlar kod yazmaz):** Her Order kapanışında audit-god review pass; ana orchestrator (operator+ben) sentez+aksiyon.
- **MANDATE 7 (üç ayağı birlikte tut):** Body değişiklikleri Mind sentinel ingest + Reflex audit-trail format'ına uyar.
- **Karpathy disiplini:** Sadece kapsamdakine dokun; "iyileştirme"den uzak dur; pluggable interfaces day 1.
- **No-mock policy (memory `project_ui_stack.md`):** Tüm testler gerçek service/runtime'a karşı; LLM dışında mock yok.

**Gözlemlenen riskler (ADR-005 §Risk register):** R1 vision güvenilirliği, R3 daemon packaging, R4 Stagehand vendor-lock; her order'da "Risks" bölümü mitigation listeliyor.

**Test budget:** Mevcut M4 baseline 1248 backend + 83 frontend. M5 hedef: ≥ 1500 backend + ≥ 130 frontend + Go daemon ≥ %80 unit coverage + 1 e2e (mocked Tailscale).

---

## 2. Order Dependency Graph

```
Order 1 (Pre-M5 infra prereq) ─────┐
                                   │
Order 2 (Sandbox + Warden) ────────┼─────┐
                                   │     │
Order 3 (Vision Pipeline) ─────────┼─────┤
                                   │     │
Order 4 (Tools body.*) ────────────┴─────┤
                                         │
Order 5 (Web driver) ────────────────────┤
Order 6 (Mobile drivers) ────────────────┤
Order 7 (Desktop drivers) ───────────────┤
                                         │
Order 8 (Daemon Go) ─────────────────────┤
                                         │
                                         ▼
Order 9 (Cockpit + Provider Auth UI) ──── M5 close-out
                                         + audit-god review
                                         + ROADMAP revize PR
                                         + manual smoke
```

**Critical path:** Order 1 → 2/3/4 paralel ilerleyebilir → 5/6/7 paralel driver implementation → 8 daemon (sıralı, çünkü tmux driver order 7'nin sonu) → 9 cockpit (tüm önceki orderları tüketir).

**Paralel pencereler:**
- O2 + O3 + O4 paralel (sandbox + vision + tools — orthogonal)
- O5 + O6 + O7 paralel (3 driver paralel; her biri O2/3/4 üzerine bina)
- O8 + O9 paralel sonuna doğru (daemon Go workspace ayrı, cockpit Next.js ayrı)

---

## 3. Pre-flight Checklist (Order 0 — verify-only)

ADR-005 §Mimari kararlar 1.MIGRATION + Ajan 14 audit'in 4 prereq blocker'ı. Implementation başlamadan **doğrulanır**:

- [ ] **packages/body/ skeleton mevcut** — Ajan 12 verify (9 boş `__init__.py` + 1 smoke test, ADR-001 §4 + §14.9). Eğer eksikse Order 1'in başında oluşturulur.
- [ ] **mlx_vlm yüklü** — `python -c "import mlx_vlm; print(mlx_vlm.__version__)"` çalışır. Memory'de "not installed in .venv" notu — verify; gerekirse `uv pip install mlx-vlm` (operator).
- [ ] **Gemma 4 E2B-it Q4_0 model dosyası** — `~/.selffork/models/gemma-4-E2B-it-q4_0/` var ve `mlx_vlm.server` ile boot edilebilir.
- [ ] **Go toolchain yüklü** (Order 8 prereq) — `go version` ≥ 1.22.
- [ ] **Tailscale CLI yüklü** + operator hesabı authorized (Order 8 prereq) — `tailscale status` çalışır.
- [ ] **Apple Developer ID veya self-signing cert** (Order 8 prereq, macOS notarize) — opsiyonel; ilk M5 demo için unsigned dev binary kabul edilir.
- [ ] **Docker yüklü** (Order 6 Android prereq) — `docker --version` çalışır.
- [ ] **Xcode + iOS Simulator** (Order 6 iOS prereq) — `xcrun simctl list devices` ≥ 1 device.
- [ ] **`pnpm` workspace ve `apps/web` testleri yeşil** — M4 baseline regression-free.
- [ ] **Backend 1248 test pass** — M4 baseline regression-free.

Eğer herhangi bir madde fail ederse Order 1 başında **çözülür** veya operator'a not düşülür (commit-able durumda olmayan environment'la implement edilmez).

---

## 4. Order detayları

### Order 1 — Pre-M5 infra prereq

**Hedef:** ADR-005 §M5-A/B/C için pre-req olan migration ve extension'ları yap. Vision drivers + sandbox + body.* tools sonraki order'ların hepsi bunlara bağımlı.

**Süre:** 3-5 gün
**Bağımlılık:** Pre-flight Order 0 geçti.

#### Sub-task 1.1 — `ChatMessage` multimodal migration

`packages/orchestrator/src/selffork_orchestrator/runtime/base.py:24-27`:

**Önceki:**
```python
ChatMessage = dict[str, str]
```

**Yeni:**
```python
from typing import TypedDict, Literal

class ContentPartText(TypedDict):
    type: Literal["text"]
    text: str

class ContentPartImageURL(TypedDict):
    type: Literal["image_url"]
    image_url: dict[str, str]  # {"url": "data:image/png;base64,..."} or http url

class ContentPartImageBytes(TypedDict):
    type: Literal["image_bytes"]
    data: bytes
    mime: Literal["image/png", "image/jpeg"]

ContentPart = ContentPartText | ContentPartImageURL | ContentPartImageBytes

class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentPart]
    name: str | None  # tool messages için
```

**Etkilenen dosyalar (impact perimeter):**
- `runtime/base.py:24-27, 91-93` — ChatMessage tip + `LLMRuntime.invoke` imza extension (`messages: list[ChatMessage]` aynı kalır, content polymorphic).
- `runtime/{ollama,llama_cpp,vllm,mlx_server}.py` — her backend'in vision parity'si:
  - **MlxServerRuntime** (`mlx_server.py`): `mlx_vlm.server` zaten multimodal endpoint serve ediyor; payload `{messages: [{role, content: [{type: "text", text}, {type: "image_url", image_url: {url}}]}]}` JSON; minimum kod değişikliği.
  - **OllamaRuntime** (`ollama.py`): `ollama.AsyncClient.chat(images=[bytes])` API; `ContentPartImageBytes` → `images` list'ine flatten; `selffork-researcher` Gemma 4 + Ollama vision compat verify edecek (Order 1.6 sub-task).
  - **VllmRuntime** (`vllm.py`): OpenAI-compat protocol; image_url native destek.
  - **LlamaCppRuntime** (`llama_cpp.py`): GGUF + multimodal projector (mmproj); Gemma 4 desteği belirsiz, M5'te `NotImplementedError` raise; gracefuldegrade text-only mode.
- 4 CLIAgent (`cli_agent/{claude_code,gemini_cli,codex,opencode,minimax_cli}.py`) — bu tipi tüketmiyor, regression riski düşük; smoke test ile valide.
- `packages/orchestrator/.../tools/base.py:55-96` `ToolContext` — text-only invocation pattern korunuyor; vision tool'ları (Order 4) farklı path.

**Yapılacaklar:**
- Migration commit-edilebilir tek atomic değişiklik olarak hazırla.
- Mevcut `ChatMessage = dict[str, str]` kullanan yerlere graceful fallback (str content → `[{type: "text", text}]` auto-promote).
- 5-6 yeni unit test: text-only / single image / multi image / image+text mixed / tool message scenarios.

#### Sub-task 1.2 — `AuditCategory` Literal extension

`packages/shared/src/selffork_shared/audit.py:28-57`:

**Yeni eklenecek 9 + 5 = 14 entry:**

```python
AuditCategory = Literal[
    # ... existing 28 entries ...
    
    # Body driver lifecycle (M5)
    "body.driver.start",
    "body.driver.stop",
    
    # Body action surface (M5)
    "body.action.invoke",       # warden henüz karar vermedi
    "body.action.executed",     # driver tamamladı
    "body.action.failed",       # exception/timeout/kill
    
    # Body permission warden (M5)
    "body.permission.requested",
    "body.permission.deny",
    
    # Body vision pipeline (M5)
    "body.vision.query",
    "body.observation",         # screenshot/AX-tree snapshot
    
    # Provider Auth UI (M5)
    "provider.auth.requested",
    "provider.auth.success",
    "provider.auth.failed",
    "provider.token.refreshed",
    "provider.token.expired",
]
```

**Yeni payload alanları (opsiyonel, geriye uyumlu):**
- `risk_tier: Literal["T0","T1","T2","T3"] | None`
- `action_type: str | None`
- `target_uri_redacted: str | None`
- `before_screenshot_ref: str | None` (path, binary değil)
- `after_screenshot_ref: str | None`
- `duration_ms: int | None`
- `warden_decision: Literal["allow","deny","approved","killed"] | None`
- `warden_reason: str | None`
- `provider: str | None` (provider.* events)

**Test:** AuditLogger.log() her yeni category ile JSONL satırı emit ediyor; existing 28 category regression yok.

#### Sub-task 1.3 — Secret redaction extension

`packages/orchestrator/src/selffork_orchestrator/lifecycle/session.py:746-772` `_SECRET_KEY_PATTERNS`:

**Yeni 5 pattern eklenir:**
```python
_SECRET_KEY_PATTERNS = (
    # ... existing 24 patterns ...
    "screenshot_b64",
    "image_b64",
    "image_url",
    "after_screenshot_b64",
    "before_screenshot_b64",
)
```

**Yeni katman `_redact_image_payload(value: bytes | str) -> str`:**
```python
def _redact_image_payload(value: bytes | str) -> str:
    """Base64 detect + truncate. Inline binary YASAK; path reference enforce."""
    if isinstance(value, bytes):
        return f"<redacted_image:{len(value)}_bytes>"
    if isinstance(value, str):
        # Base64 prefix detect
        if value.startswith(("iVBORw0KG", "/9j/", "data:image/")):
            return f"<redacted_image_base64:{len(value)}_chars>"
        # Path reference OK (e.g. /Users/.../screenshots/abc.png)
        if value.startswith(("/Users/", "/home/", "/var/")) and value.endswith((".png", ".jpg")):
            return value  # path is OK
    return value  # other types unchanged
```

**`_redact_recursive` 16-depth cap için:** `_redact_image_payload` katmanı `_redact_recursive` içinde value scan'inde çağrılır (recursion'dan önce).

**Test:** screenshot_b64 inline base64 → `<redacted_image_base64:N_chars>`; path string → unchanged; raw bytes → `<redacted_image:N_bytes>`.

#### Sub-task 1.4 — `ToolContext` extension

`packages/orchestrator/src/selffork_orchestrator/tools/base.py:55-96`:

```python
@dataclass(frozen=True, slots=True)
class ToolContext:
    # ... existing fields ...
    body_driver: object | None = None  # selffork_body.drivers.UnifiedDriver protocol
    vision_runtime: object | None = None  # MultimodalLLMRuntime adapter
    permission_warden: object | None = None  # selffork_body.sandbox.PermissionWarden
```

Frozen dataclass slots — yeni field eklenmesi mevcut tüm tool'lar için None default; geriye uyumlu, breaking change yok.

**Test:** mevcut 13 tool ToolContext oluşturma regression-free; body_driver=None ile çalışmaya devam.

#### Sub-task 1.5 — Screenshot persistence path infrastructure

`packages/body/storage/screenshots.py` (yeni dosya):

```python
@dataclass(frozen=True)
class ScreenshotRef:
    path: Path
    sha256: str
    timestamp: datetime
    session_id: str
    project_slug: str | None  # None = orphan
    width: int
    height: int
    bytes_size: int

class ScreenshotStore:
    def __init__(self, root: Path = Path.home() / ".selffork"):
        self.root = root
    
    def write(self, image_bytes: bytes, session_id: str, project_slug: str | None = None) -> ScreenshotRef:
        """SHA256 dedup + path persistence. Returns ref with metadata."""
        # ...
    
    def cleanup(self, retention_days: int = 7):
        """Auto-cleanup older than retention_days."""
        # ...
```

Path pattern (ADR-005 §M5-D3):
- `~/.selffork/projects/<slug>/screenshots/<session_id>/<ts>_<sha8>.png`
- Orphan: `~/.selffork/screenshots/orphan/<session_id>/<ts>_<sha8>.png`

**Test:** dedup sha256, retention auto-cleanup, project vs orphan path branching.

#### Sub-task 1.6 — `selffork-researcher` Gemma 4 + Ollama vision compat verify

Order 1 sırasında **paralel** olarak `selffork-researcher` ajanı sallanır:
- Gemma 4 E2B-it Q4_0 Ollama'da `images` parametresini destekliyor mu?
- mlx-community/gemma-4-E2B-it-4bit MLX swift impl + mlx_vlm.server farkı?
- Linux server-side Gemma 4 vision parity (MLX yok, vLLM/Ollama)?

Sonuç Order 3 vision pipeline implementasyonuna feed edilir.

#### Sub-task 1.7 — Tests

`packages/shared/tests/test_audit.py` ekleme: yeni 14 category emit smoke + payload field genişleme.
`packages/orchestrator/tests/runtime/test_chat_message_migration.py` (yeni): TypedDict polymorphism + auto-promote tests.
`packages/orchestrator/tests/lifecycle/test_redaction.py` ekleme: image redaction katmanı.
`packages/body/tests/storage/test_screenshots.py` (yeni): ScreenshotStore CRUD + cleanup.

#### Acceptance criteria — Order 1
- [ ] ChatMessage migration commit-able tek PR; M3+M4 1331 test pass regression-free.
- [ ] AuditCategory Literal 14 yeni entry + opsiyonel payload alanları; existing audit emit regression-free.
- [ ] _SECRET_KEY_PATTERNS 5 yeni + _redact_image_payload katman; smoke test inline binary YOK.
- [ ] ToolContext 3 yeni field None-default; mevcut 13 tool regression-free.
- [ ] ScreenshotStore CRUD + 7-gün retention auto-cleanup.
- [ ] selffork-researcher Gemma 4 Ollama vision compat raporu Order 3'e input.

#### Risks — Order 1
- ChatMessage migration regression — 4 CLIAgent + tools layer + 2 dashboard router etkilenir. Mitigation: smoke test 5-6 path, atomic PR.
- Ollama Gemma 4 vision unsupported çıkarsa — Linux server fallback path kararı (MLX yok). Mitigation: vLLM primary Linux fallback, Ollama opsiyonel.

---

### Order 2 — Permission Warden + Sandbox foundation

**Hedef:** `packages/body/sandbox/` action-level permission warden (3-mod state machine + 4-tier risk_tier + kill switch + watchdog) + OS-tier sandbox-exec (macOS) ve bubblewrap (Linux) backend'leri.

**Süre:** 5-7 gün
**Bağımlılık:** Order 1 (AuditCategory + ToolContext + screenshot store) tamamlandı.

#### Sub-task 2.1 — `packages/body/sandbox/risk_taxonomy.py`

```python
from typing import Literal
from dataclasses import dataclass

RiskTier = Literal["T0", "T1", "T2", "T3"]

@dataclass(frozen=True)
class RiskClassification:
    tier: RiskTier
    description: str
    approval_gate: Literal["auto", "on_request", "always_required", "two_key"]
    timeout_sec: int  # default deny on timeout

# Action → tier mapping (default registry; override per-session)
DEFAULT_ACTION_TIERS: dict[str, RiskTier] = {
    # T0 — Read-only, idempotent
    "screenshot": "T0",
    "scroll": "T0",
    "ax_tree": "T0",
    "read_dom": "T0",
    "list_processes": "T0",
    
    # T1 — Local mutation, geri alınabilir
    "click": "T1",
    "type": "T1",
    "press_key": "T1",
    "swipe": "T1",
    "navigate": "T1",  # allowlisted domain
    "workspace_file_write": "T1",
    
    # T2 — Yan etki yüksek
    "shell_exec": "T2",
    "file_write_outside_workspace": "T2",
    "navigate_new_domain": "T2",
    "app_launch": "T2",
    "install_apk": "T2",
    "evaluate_js": "T2",
    "applescript": "T2",
    
    # T3 — Maliyet/hesap riski
    "payment_form_submit": "T3",
    "credential_input": "T3",
    "account_login": "T3",
    "network_egress_unknown_host": "T3",
}
```

#### Sub-task 2.2 — `packages/body/sandbox/warden.py` (3-mod state machine)

```python
from enum import Enum
from typing import Literal

class WardenMode(Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"

class WardenState(Enum):
    INACTIVE = "inactive"
    ARMED = "armed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    AUDITED = "audited"
    DENIED = "denied"
    KILLED = "killed"

@dataclass
class PermissionRequest:
    request_id: str
    session_id: str
    action_type: str
    risk_tier: RiskTier
    target_uri: str | None
    args_summary: dict
    requested_at: datetime

@dataclass
class PermissionDecision:
    approved: bool
    decision: Literal["allow", "deny", "approved", "killed"]
    reason: str
    decided_at: datetime
    decided_by: Literal["auto", "operator", "warden", "watchdog"]

class PermissionWarden:
    def __init__(
        self,
        mode: WardenMode = WardenMode.WORKSPACE_WRITE,
        allowed_domains: set[str] | None = None,
        default_timeout_sec: int = 30,
        audit_logger: AuditLogger | None = None,
    ):
        self.mode = mode
        self.allowed_domains = allowed_domains or set()
        self.default_timeout_sec = default_timeout_sec
        self.audit = audit_logger
        self._state = WardenState.ARMED
        self._pending: dict[str, PermissionRequest] = {}
    
    async def request(self, req: PermissionRequest) -> PermissionDecision:
        # ... 3-mod logic + 4-tier gate + timeout + audit emit
    
    async def operator_decide(self, request_id: str, approved: bool, reason: str) -> None:
        # Cockpit "Approve/Deny" button + Telegram bridge handler
    
    def kill(self, reason: str) -> None:
        # SIGKILL signal → state KILLED → all pending → DENIED
```

**3-mod gate logic:**

| Mod | T0 | T1 | T2 | T3 |
|---|---|---|---|---|
| `read_only` | auto-allow | auto-deny | auto-deny | auto-deny |
| `workspace_write` | auto-allow | auto-allow | always_required (operator confirm) | always_required + 2-key |
| `danger_full_access` | auto-allow | auto-allow | auto-allow (logged) | always_required + 2-key |

**Domain comparison (CVE-2025-47241 mitigation):**
- `urlparse` netloc → strip userinfo (`@` öncesi atla) → strip port → lowercase → IDN punycode normalize.
- Pre-flight + post-redirect + new-tab check.
- Block edilen URL → audit `body.permission.deny{action_type, target_uri_redacted}` + `about:blank` redirect.

#### Sub-task 2.3 — `packages/body/sandbox/kill_switch.py` (BodyWatchdog)

```python
class BodyWatchdog:
    def __init__(
        self,
        warden: PermissionWarden,
        max_session_duration_sec: int = 1800,
        idle_timeout_sec: int = 120,
    ):
        # ...
    
    async def start_session(self, session_id: str, driver_pid: int) -> None:
        # Track driver process group (setsid'd subprocess)
    
    async def heartbeat(self, session_id: str) -> None:
        # Reset idle timer on each action
    
    async def check_limits(self) -> list[str]:
        # Return list of session_ids exceeding max_duration or idle_timeout
    
    def kill_session(self, session_id: str, reason: str) -> None:
        # SIGKILL process group; emit body.action.failed warden_decision="killed"
```

**Operator hook entries:**
- Cockpit "Stop" button → POST `/api/body/sessions/<id>/stop` → `BodyWatchdog.kill_session()`.
- Telegram bridge `/stop <session_id>` → same endpoint.
- Global SIGINT (Ctrl+C in orchestrator CLI) → `BodyWatchdog.kill_all()`.

#### Sub-task 2.4 — OS-tier sandbox backends

`packages/orchestrator/src/selffork_orchestrator/sandbox/seatbelt_sandbox.py` (yeni):

```python
class SeatbeltSandbox(Sandbox):
    """macOS sandbox-exec backend. SBPL profile generator."""
    
    SBPL_TEMPLATE = """
    (version 1)
    (deny default)
    (allow file-read* (subpath "/Users/{user}/.selffork"))
    (allow file-write* (subpath "/Users/{user}/.selffork/projects/{slug}"))
    (allow network-outbound (remote tcp "*:443"))  ; HTTPS only by default
    {extra_rules}
    """
    
    async def exec(self, command: list[str], extra_rules: str = "") -> SandboxProcess:
        # Generate profile to temp file → invoke sandbox-exec -f profile.sb command
```

`packages/orchestrator/src/selffork_orchestrator/sandbox/bubblewrap_sandbox.py` (yeni):

```python
class BubblewrapSandbox(Sandbox):
    """Linux bubblewrap user-namespace sandbox + socat egress proxy."""
    
    async def exec(self, command: list[str], allowed_domains: set[str] | None = None) -> SandboxProcess:
        # bwrap --unshare-all --share-net --ro-bind / / --bind ~/.selffork ~/.selffork command
        # Egress proxy via socat allowlisting domains (Anthropic Claude Code pattern)
```

**Factory update:** `sandbox/factory.py:14-26` `_BACKENDS` dict:
```python
_BACKENDS: dict[str, type[Sandbox]] = {
    "subprocess": SubprocessSandbox,
    "docker": DockerSandbox,
    "seatbelt": SeatbeltSandbox,      # YENI
    "bubblewrap": BubblewrapSandbox,  # YENI
}
```

#### Sub-task 2.5 — Cockpit "Stop" + Telegram /stop hook

Backend: `packages/orchestrator/src/selffork_orchestrator/dashboard/body_router.py` (yeni):
- POST `/api/body/sessions/<id>/stop` → BodyWatchdog.kill_session.
- GET `/api/body/sessions` → list active sessions.
- WS `/ws/body/sessions/<id>` → permission requests stream.

Telegram bridge: `packages/orchestrator/.../telegram/body_handler.py` (yeni):
- `/stop <session_id>` → POST endpoint.
- `/approve <request_id>` veya `/deny <request_id>` → Operator approval channel.

Frontend stub: `apps/web/lib/body/stop.ts` — REST client. Tam UI Order 9'da.

#### Sub-task 2.6 — Tests

`packages/body/tests/sandbox/test_warden.py` (yeni):
- 3 mod x 4 tier matrix → 12 case + edge cases (timeout deny, operator approve, kill).
- Domain comparison CVE-2025-47241 paterni (userinfo, port, IDN).
- BodyWatchdog max-duration + idle-timeout.

`packages/body/tests/sandbox/test_kill_switch.py` (yeni):
- SIGKILL process group ile child exit verify.
- Audit emit warden_decision="killed".

`packages/orchestrator/tests/sandbox/test_seatbelt.py` (yeni, macOS-only — pytest skipif):
- Profile generation + sandbox-exec smoke (basic file-read deny).

`packages/orchestrator/tests/sandbox/test_bubblewrap.py` (yeni, Linux-only — pytest skipif):
- bwrap subprocess smoke + egress allowlist.

#### Acceptance criteria — Order 2
- [ ] PermissionWarden 3-mod x 4-tier state machine 12 case test pass.
- [ ] CVE-2025-47241 mitigation: domain compare userinfo+port+IDN normalize 6 case test pass.
- [ ] BodyWatchdog max-duration + idle-timeout SIGKILL container'a (agent'a değil).
- [ ] SeatbeltSandbox macOS dev'de smoke geçti (file-read deny verified).
- [ ] BubblewrapSandbox Linux CI'da smoke geçti.
- [ ] Cockpit "Stop" REST endpoint + Telegram /stop hook canlı (UI tam Order 9).

#### Risks — Order 2
- macOS sandbox-exec deprecated warning'ı (Apple 2017'den beri "deprecated" diyor ama hâlâ default sandbox tooling). Mitigation: Apple App Sandbox (entitlements) M6+ değerlendir; SBPL M5 default.
- bwrap kullanıcı namespace gerektirir (rootless OK ama /etc/subuid+subgid setup gerekebilir). Mitigation: install-daemon-ubuntu.md doc'a setup talimatı.

---

### Order 3 — Vision Pipeline (Gemma 4 multimodal)

**Hedef:** `packages/body/vision/` — Gemma 4 E2B-it Q4_0 multimodal pipeline; cross-platform screenshot capture; Tier-1/2/3 prompt strategy; <2sn p95 latency hedef.

**Süre:** 5-7 gün
**Bağımlılık:** Order 1 (ChatMessage migration) + selffork-researcher Gemma 4 Ollama compat raporu.

#### Sub-task 3.1 — `packages/body/vision/screenshot.py`

Cross-platform screenshot capture:

```python
from abc import ABC, abstractmethod
from pathlib import Path

class ScreenshotCapture(ABC):
    @abstractmethod
    async def capture(self, rect: tuple[int,int,int,int] | None = None) -> bytes:
        ...

class MacOSScreenshotCapture(ScreenshotCapture):
    """screencapture -x -t png subprocess + AVFoundation fallback."""
    
    async def capture(self, rect=None) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            cmd = ["screencapture", "-x", "-t", "png"]
            if rect:
                cmd += ["-R", f"{rect[0]},{rect[1]},{rect[2]},{rect[3]}"]
            cmd.append(path)
            await asyncio.create_subprocess_exec(*cmd)
            return Path(path).read_bytes()
        finally:
            Path(path).unlink(missing_ok=True)

class LinuxScreenshotCapture(ScreenshotCapture):
    """grim (Wayland) + scrot (X11) fallback chain."""
    # ...

class WindowsScreenshotCapture(ScreenshotCapture):
    """PowerShell System.Drawing + mss fallback."""
    # ...

class IosSimulatorScreenshotCapture(ScreenshotCapture):
    """xcrun simctl io booted screenshot."""
    # ...

class AndroidScreenshotCapture(ScreenshotCapture):
    """uiautomator2 device.screenshot()."""
    # ...

class WebScreenshotCapture(ScreenshotCapture):
    """Playwright page.screenshot(full_page=True)."""
    # ...

def get_screenshot_capture(driver_type: str) -> ScreenshotCapture:
    # Factory dispatch
```

#### Sub-task 3.2 — `packages/body/vision/preprocess.py`

```python
from PIL import Image
from io import BytesIO

@dataclass(frozen=True)
class PreprocessConfig:
    target_long_edge: int = 1024  # multiples of 48 (Gemma 4 kuralı; 1024 round)
    token_budget: Literal[70, 140, 280, 560, 1120] = 280
    roi: tuple[int,int,int,int] | None = None  # (x,y,w,h) crop
    format: Literal["png", "jpeg"] = "png"

def preprocess(image_bytes: bytes, cfg: PreprocessConfig) -> bytes:
    img = Image.open(BytesIO(image_bytes))
    if cfg.roi:
        img = img.crop((cfg.roi[0], cfg.roi[1], cfg.roi[0]+cfg.roi[2], cfg.roi[1]+cfg.roi[3]))
    if cfg.target_long_edge:
        long_edge = max(img.size)
        if long_edge > cfg.target_long_edge:
            scale = cfg.target_long_edge / long_edge
            new_size = (int(img.size[0]*scale), int(img.size[1]*scale))
            # Round to multiples of 48 (Gemma 4 patch density)
            new_size = (max(48, (new_size[0]//48)*48), max(48, (new_size[1]//48)*48))
            img = img.resize(new_size, Image.LANCZOS)
    out = BytesIO()
    img.save(out, format=cfg.format.upper(), optimize=True)
    return out.getvalue()

def delta_image(before: bytes, after: bytes) -> bytes:
    """Pixel-diff between before/after for state-change verification."""
    # Numpy diff + thresholding → highlighted change regions PNG
```

#### Sub-task 3.3 — `packages/body/vision/prompt.py`

```python
TIER1_PROMPT_TEMPLATE = """\
You are a UI control agent. Look at the screenshot and decide the next action.

Goal: {goal}

Available actions:
- click(target_description, bbox?, button?)
- type(text, target?)
- swipe(direction, amount?)
- scroll(direction, amount?)
- press_key(key_combo)
- wait(ms)

Return ONLY a single JSON object:
{{
  "action": "click" | "type" | "swipe" | "scroll" | "press_key" | "wait",
  "target": "<short description of element>",
  "bbox": [x, y, w, h] | null,
  "args": {{...action-specific args...}},
  "confidence": 0.0..1.0,
  "reason": "<one sentence>"
}}

Do not include any text before or after the JSON."""

TIER2_PROMPT_TEMPLATE = """\
{tier1_template}

Additional context:
DOM/AX-tree summary:
{ax_tree_text}

The previous Tier-1 attempt had low confidence ({prev_confidence}). Re-examine the cropped region carefully."""

TIER3_PROMPT_TEMPLATE = """\
{tier2_template}

Set-of-Marks overlay applied. Click target by index number visible on screenshot.
Available marks: {marks_summary}"""

def build_prompt(
    tier: Literal[1,2,3],
    goal: str,
    ax_tree_text: str | None = None,
    prev_confidence: float | None = None,
    marks_summary: str | None = None,
) -> str:
    # Template dispatch
```

#### Sub-task 3.4 — `packages/body/vision/runtime.py` (MultimodalLLMRuntime)

```python
from selffork_orchestrator.runtime.base import LLMRuntime, ChatMessage
from typing import Protocol

class MultimodalLLMRuntime(Protocol):
    async def invoke_with_images(
        self,
        messages: list[ChatMessage],
        images: list[bytes],
        max_tokens: int = 256,
        temperature: float = 0.0,
        stop: list[str] | None = None,
    ) -> str:
        ...

class MlxVlmAdapter:
    """Adapter wrapping mlx_vlm.server endpoint."""
    
    def __init__(self, server_url: str = "http://127.0.0.1:8080"):
        self.server_url = server_url
    
    async def invoke_with_images(self, messages, images, **kwargs) -> str:
        # POST to mlx_vlm.server /v1/chat/completions with multimodal payload
        payload = {
            "messages": [
                {"role": m["role"], "content": _to_multimodal_content(m, images)}
                for m in messages
            ],
            "max_tokens": kwargs.get("max_tokens", 256),
            "temperature": kwargs.get("temperature", 0.0),
        }
        # ...

class OllamaVlmAdapter:
    """Ollama AsyncClient with images list."""
    # ...

def get_vision_runtime(backend: Literal["mlx_vlm", "ollama", "vllm"]) -> MultimodalLLMRuntime:
    # Factory dispatch
```

**Tier-1/2/3 fallback orchestration:**

```python
@dataclass
class VisionDecision:
    action: str
    target: str
    bbox: tuple[int,int,int,int] | None
    args: dict
    confidence: float
    reason: str
    tier: Literal[1, 2, 3]
    duration_ms: int

class VisionOrchestrator:
    def __init__(self, runtime: MultimodalLLMRuntime, audit: AuditLogger):
        self.runtime = runtime
        self.audit = audit
        self.tier1_threshold = 0.7
    
    async def decide(
        self,
        screenshot: bytes,
        goal: str,
        ax_tree_text: str | None = None,
    ) -> VisionDecision:
        # Tier-1 attempt
        t1 = await self._tier1(screenshot, goal)
        if t1.confidence >= self.tier1_threshold:
            return t1
        
        # Tier-2 fallback (ROI + DOM hint + token budget bump)
        t2 = await self._tier2(screenshot, goal, ax_tree_text, t1.confidence)
        if t2.confidence >= self.tier1_threshold:
            return t2
        
        # Tier-3 last resort (SoM overlay)
        return await self._tier3(screenshot, goal, ax_tree_text, t2.confidence)
```

**Audit emit per call:**
```python
self.audit.log("body.vision.query", {
    "tier": decision.tier,
    "duration_ms": decision.duration_ms,
    "confidence": decision.confidence,
    "before_screenshot_ref": screenshot_ref.path,
    "prompt_template_id": f"tier{decision.tier}_v1",
    "output_action": decision.action,
})
```

#### Sub-task 3.5 — Held-out eval (30-task corpus)

`benchmarks/m5_vision_eval/` (yeni dir):
- 30 task corpus (10 web + 10 desktop + 5 Android + 5 iOS sim).
- Her task: screenshot.png + goal.txt + expected_action.json.
- `pytest benchmarks/m5_vision_eval/run_eval.py` — accuracy report.
- Threshold: ≥ %85 action-precision (locate-by-label JSON output reliability).

Eğer < %85 ise R1 risk tetikleniyor → operator karar (vision iter M6, daemon-only finalize).

#### Sub-task 3.6 — Latency measurement infrastructure

`packages/body/vision/profiling.py`:

```python
@dataclass
class LatencyBreakdown:
    image_encode_ms: float
    prefill_ms: float
    decode_ms: float
    total_ms: float

async def profile_call(runtime, screenshot: bytes, goal: str) -> LatencyBreakdown:
    # Time each phase via mlx_vlm.server stream events
```

Cockpit Body tab'da p50/p95 latency canlı gauge (UI Order 9).

#### Acceptance criteria — Order 3
- [ ] MultimodalLLMRuntime mlx_vlm + Ollama adapter implementations çalışıyor.
- [ ] ChatMessage migration ile end-to-end vision call (screenshot+goal → JSON action) p95 < 2sn (held-out eval).
- [ ] Tier-1/2/3 fallback chain manual smoke 3 senaryo (yüksek-confidence T1, düşük T1→T2 bump, edge case T3 SoM).
- [ ] 30-task held-out eval ≥ %85 action precision (R1 gate); < %85 ise operator notify.
- [ ] `body.vision.query` + `body.observation` audit emit JSONL'a düşüyor; binary inline YOK.
- [ ] LatencyBreakdown profiling — encode/prefill/decode/total ms surface.

#### Risks — Order 3
- **R1 (ADR-005):** Gemma 4 E2B Q4_0 vision güvenilirsiz (held-out eval < %85). Mitigation: Bouncing Back path — vision drivers M6'a iter, M5 = daemon-only. Karar gate Order 3 sonu.
- Q4_0 + SoM tested değil; Tier-3 fallback başarısız olabilir. Mitigation: Tier-3 opsiyonel; Tier-1/2 yetiyorsa M5'e yetiyor.
- mlx_vlm.server vendor coupling (Apple Silicon only); Linux server-side fallback (vLLM/Ollama) verify gerek (Order 1.6 raporu).

---

### Order 4 — Tools registry + body.* tools

**Hedef:** `packages/orchestrator/.../tools/body.py` — 10 body.* tool ToolSpec ile + ToolRegistry'ye plug-in. Jr autopilot bu tool'ları MCP-style `<selffork-tool-call>` ile çağırabilir.

**Süre:** 3-4 gün
**Bağımlılık:** Order 1 (ToolContext extension) + Order 2 (PermissionWarden) + Order 3 (VisionOrchestrator).

#### Sub-task 4.1 — ToolSpec definitions

`packages/orchestrator/src/selffork_orchestrator/tools/body.py` (yeni):

```python
from selffork_orchestrator.tools.base import ToolSpec, ToolArgs, ToolContext
from pydantic import BaseModel, Field
from typing import Literal

class BodyClickArgs(ToolArgs):
    target: str = Field(..., description="Element selector or natural language description")
    bbox: tuple[int,int,int,int] | None = Field(None, description="Optional bounding box (x,y,w,h)")
    button: Literal["left", "right"] = Field("left")

class BodyTypeArgs(ToolArgs):
    text: str = Field(..., description="Text to type")
    target: str | None = Field(None, description="Target field; None = active focus")

class BodyScreenshotArgs(ToolArgs):
    rect: tuple[int,int,int,int] | None = Field(None)

class BodyScrollArgs(ToolArgs):
    direction: Literal["up","down","top","bottom","left","right"] = "down"
    amount: int = Field(300, ge=10, le=10000)

class BodySwipeArgs(ToolArgs):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration_ms: int = Field(250, ge=50, le=5000)

class BodyAppLaunchArgs(ToolArgs):
    bundle_id: str  # macOS bundle ID, Android package, iOS bundle ID

class BodyPressKeyArgs(ToolArgs):
    key_combo: str  # "cmd+t", "ctrl+a", "back", "home"

class BodyStorageStateSaveArgs(ToolArgs):
    provider: str  # "claude_pro" | "codex" | "gemini" | "opencode" | "mmx"
    project_slug: str | None = None

class BodyStorageStateLoadArgs(ToolArgs):
    provider: str
    project_slug: str | None = None

class BodyAxTreeArgs(ToolArgs):
    bundle_id: str | None = None  # macOS app filter; None = full system tree
```

```python
async def _body_click(ctx: ToolContext, args: BodyClickArgs) -> str:
    if not ctx.body_driver:
        return json.dumps({"ok": False, "error": "no body_driver in context"})
    if not ctx.permission_warden:
        return json.dumps({"ok": False, "error": "no permission_warden"})
    
    decision = await ctx.permission_warden.request(PermissionRequest(
        request_id=str(uuid.uuid4()),
        session_id=ctx.session_id,
        action_type="click",
        risk_tier="T1",
        target_uri=args.target,
        args_summary={"bbox": args.bbox, "button": args.button},
        requested_at=datetime.now(),
    ))
    if not decision.approved:
        return json.dumps({"ok": False, "error": "permission denied", "reason": decision.reason})
    
    started = time.monotonic()
    try:
        await ctx.body_driver.click(args.target, args.bbox, args.button)
        duration_ms = int((time.monotonic() - started) * 1000)
        ctx.audit.log("body.action.executed", {
            "action_type": "click",
            "target_uri_redacted": args.target,
            "duration_ms": duration_ms,
            "risk_tier": "T1",
        })
        return json.dumps({"ok": True, "duration_ms": duration_ms})
    except Exception as exc:
        ctx.audit.log("body.action.failed", {
            "action_type": "click",
            "exception": exc.__class__.__name__,
            "risk_tier": "T1",
        })
        return json.dumps({"ok": False, "error": str(exc)})

# Similar for type, screenshot, scroll, swipe, app_launch, press_key, storage_state_save/load, ax_tree
```

#### Sub-task 4.2 — `build_body_tools()` factory

```python
def build_body_tools() -> list[ToolSpec]:
    return [
        ToolSpec(name="body_click", args_model=BodyClickArgs, handler=_body_click,
                 description="Click on UI element via vision/AX-tree locator."),
        ToolSpec(name="body_type", args_model=BodyTypeArgs, handler=_body_type, ...),
        ToolSpec(name="body_screenshot", args_model=BodyScreenshotArgs, handler=_body_screenshot, ...),
        ToolSpec(name="body_scroll", args_model=BodyScrollArgs, handler=_body_scroll, ...),
        ToolSpec(name="body_swipe", args_model=BodySwipeArgs, handler=_body_swipe, ...),
        ToolSpec(name="body_app_launch", args_model=BodyAppLaunchArgs, handler=_body_app_launch, ...),
        ToolSpec(name="body_press_key", args_model=BodyPressKeyArgs, handler=_body_press_key, ...),
        ToolSpec(name="body_storage_state_save", args_model=BodyStorageStateSaveArgs, handler=_body_storage_state_save, ...),
        ToolSpec(name="body_storage_state_load", args_model=BodyStorageStateLoadArgs, handler=_body_storage_state_load, ...),
        ToolSpec(name="body_ax_tree", args_model=BodyAxTreeArgs, handler=_body_ax_tree, ...),
    ]
```

#### Sub-task 4.3 — `tools/__init__.py` registry update

```python
def build_default_registry() -> ToolRegistry:
    return ToolRegistry(specs=[
        *build_kanban_tools(),
        *build_mind_tools(),
        *build_quota_tools(),
        *build_session_tools(),
        *build_autopilot_tools(),
        *build_body_tools(),  # YENI
    ])
```

#### Sub-task 4.4 — Jr autopilot tool surface extension

`packages/orchestrator/src/selffork_orchestrator/cli_agent/jr_autopilot.py`:
- 11-tool surface (M3) → 21-tool surface (M5: 11 + 10 body.*).
- Jr prompt template'inde body.* tool listesi ve usage examples eklenir.

#### Sub-task 4.5 — Tests

`packages/orchestrator/tests/tools/test_body.py` (yeni):
- 10 ToolSpec args validation (Pydantic regression).
- Each handler stubbed body_driver + permission_warden ile test:
  - Permission deny path.
  - Permission allow → driver call → audit emit.
  - Driver exception → body.action.failed audit.
- Integration: ToolRegistry.invoke() round-trip.

`packages/orchestrator/tests/cli_agent/test_jr_autopilot_body.py` (yeni):
- Jr prompt'unda body.* tool surface görünüyor.
- `<selffork-tool-call>{"name": "body_click", ...}</selffork-tool-call>` parse + dispatch.

#### Acceptance criteria — Order 4
- [ ] 10 body.* ToolSpec'i + Pydantic args validation.
- [ ] PermissionWarden integration: deny path + allow path + audit emit smoke.
- [ ] ToolRegistry.invoke() body_click stub driver ile end-to-end geçti.
- [ ] Jr autopilot prompt template body.* tool surface'i sergilendi; tool-call parsing regression-free.
- [ ] Mevcut 13 tool (M3 11-tool + M2 2 mind tool) regression-free.

#### Risks — Order 4
- ToolContext frozen dataclass extension breaking change ihtimali — body_driver=None default ile mitigate edildi.
- Jr prompt size 21 tool listesiyle context window'u zorlayabilir. Mitigation: tool listesi compact format (bir satır per tool); detailed schema sadece invoke'da expand.

---

### Order 5 — Web Driver

**Hedef:** `packages/body/drivers/web/` — Playwright + browser-use referans paterni + Stagehand v3 hibrid (vendor-test verify) + SecurityWatchdog + storage_state per provider.

**Süre:** 7-10 gün
**Bağımlılık:** Order 1+2+3+4 tamamlandı.

#### Sub-task 5.1 — `packages/body/drivers/web/playwright_driver.py`

```python
from playwright.async_api import async_playwright, Page, BrowserContext
from selffork_body.sandbox import PermissionWarden
from selffork_body.vision import VisionOrchestrator

class PlaywrightWebDriver:
    def __init__(
        self,
        warden: PermissionWarden,
        vision: VisionOrchestrator,
        headless: bool = True,
        storage_state: Path | None = None,
        allowed_domains: set[str] | None = None,
    ):
        self.warden = warden
        self.vision = vision
        self.headless = headless
        self.storage_state = storage_state
        self.allowed_domains = allowed_domains or set()
        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
    
    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            storage_state=self.storage_state,
        )
        self._page = await self._context.new_page()
        # SecurityWatchdog wire
        self._page.on("framenavigated", self._on_navigated)
        self._page.on("popup", self._on_popup)
    
    async def goto(self, url: str) -> None:
        # Domain check via warden
        # ...
    
    async def click(self, target: str, bbox=None, button="left") -> None:
        # Tier-1: try selector via DOM extractor
        # Tier-2: vision fallback if selector failed
        # ...
    
    async def screenshot(self, full_page=True) -> bytes:
        return await self._page.screenshot(full_page=full_page, type="png")
    
    async def storage_state_save(self, path: Path) -> None:
        state = await self._context.storage_state()
        path.write_text(json.dumps(state))
    
    async def stop(self) -> None:
        await self._context.close()
        await self._browser.close()
        await self._playwright.stop()
```

#### Sub-task 5.2 — `packages/body/drivers/web/security_watchdog.py`

browser-use `security_watchdog.py:22-92` paterni reimplement (kod kopyalama YOK, paradigma referans):

```python
class SecurityWatchdog:
    def __init__(self, allowed_domains: set[str], audit: AuditLogger):
        self.allowed_domains = allowed_domains
        self.audit = audit
    
    def check_url(self, url: str) -> bool:
        # urlparse → strip userinfo → strip port → lowercase → IDN normalize
        # Compare against allowed_domains (with subdomain match)
        # CVE-2025-47241 mitigation
    
    async def on_framenavigated(self, frame):
        if not self.check_url(frame.url):
            await frame.evaluate("window.location.href = 'about:blank'")
            self.audit.log("body.permission.deny", {"target_uri_redacted": frame.url})
    
    async def on_popup(self, popup):
        if not self.check_url(popup.url):
            await popup.close()
            self.audit.log("body.permission.deny", {"target_uri_redacted": popup.url, "reason": "popup_blocked"})
```

#### Sub-task 5.3 — `packages/body/drivers/web/storage_state.py`

```python
class WebStorageStateManager:
    def __init__(self, root: Path = Path.home() / ".selffork"):
        self.root = root
    
    def path_for(self, provider: str, project_slug: str | None = None) -> Path:
        if project_slug:
            return self.root / "projects" / project_slug / "auth" / f"{provider}.json"
        return self.root / "auth-cache" / f"{provider}.json"
    
    async def save(self, context: BrowserContext, provider: str, project_slug: str | None = None) -> Path:
        path = self.path_for(provider, project_slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = await context.storage_state()
        path.write_text(json.dumps(state, indent=2))
        return path
    
    async def load_into(self, browser, provider: str, project_slug: str | None = None) -> BrowserContext:
        path = self.path_for(provider, project_slug)
        if not path.exists():
            return await browser.new_context()
        return await browser.new_context(storage_state=str(path))
```

**30sn auto-save watchdog (browser-use `storage_state_watchdog.py:25-86` paterni reimpl):**

```python
class StorageStateAutoSaveTask:
    def __init__(self, manager: WebStorageStateManager, context: BrowserContext, provider: str, interval_sec: int = 30):
        self.manager = manager
        self.context = context
        self.provider = provider
        self.interval = interval_sec
        self._task: asyncio.Task | None = None
        self._last_state_hash = ""
    
    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
    
    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            state = await self.context.storage_state()
            state_hash = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
            if state_hash != self._last_state_hash:
                await self.manager.save(self.context, self.provider)
                self._last_state_hash = state_hash
```

#### Sub-task 5.4 — `packages/body/drivers/web/dom_extractor.py`

browser-use `buildDomTree.js:1-250` paterni reimpl (Apache 2.0 modify+attribute kuralında):

```python
DOM_TREE_JS = """
(() => {
    const interactiveTags = ['a', 'button', 'input', 'select', 'textarea'];
    const elements = [];
    let index = 0;
    
    function walk(node) {
        if (node.nodeType !== 1) return;  // not element
        const tag = node.tagName.toLowerCase();
        const isInteractive = interactiveTags.includes(tag) ||
            node.onclick || node.getAttribute('role') === 'button';
        
        if (isInteractive && node.offsetParent !== null) {
            const rect = node.getBoundingClientRect();
            elements.push({
                index: index++,
                tag,
                text: node.innerText?.slice(0, 100) || '',
                attributes: {
                    id: node.id,
                    class: node.className,
                    role: node.getAttribute('role'),
                    'aria-label': node.getAttribute('aria-label'),
                },
                bbox: [rect.x, rect.y, rect.width, rect.height],
            });
        }
        for (const child of node.children) walk(child);
    }
    walk(document.body);
    return elements;
})()
"""

async def extract_dom_tree(page: Page) -> list[dict]:
    return await page.evaluate(DOM_TREE_JS)
```

#### Sub-task 5.5 — Stagehand v3 vendor-test (R4 mitigation)

`packages/body/drivers/web/stagehand_adapter.py` (verify-then-implement):

Order 5 başında 1-2 günlük vendor-test:
- Stagehand v3 (MIT) lokal Playwright + lokal LLM ile çalışıyor mu? (Browserbase olmadan)
- `stagehand.act(prompt)` `stagehand.observe()` `stagehand.extract()` Gemma 4 ile compatible mi?
- Action-replay caching gerçekten lokal mi (cloud sync'siz)?

Eğer **vendor-lock** çıkarsa → Stagehand opsiyonel, custom DOM extraction (5.4) primary.
Eğer **clean lokal path** çıkarsa → Stagehand adapter implement.

#### Sub-task 5.6 — Tests

`packages/body/tests/drivers/web/test_playwright_driver.py` (yeni):
- pytest-playwright ile lokal HTML fixture (browser-use no-mock paterni).
- 5 senaryo: navigate + click + type + screenshot + storage_state save/load.

`packages/body/tests/drivers/web/test_security_watchdog.py` (yeni):
- 6 case: allowed domain pass, blocked domain redirect, popup block, redirect-after navigate, port stripping, IDN normalize.

`packages/body/tests/drivers/web/test_storage_state.py` (yeni):
- save/load round-trip, auto-save 30sn watchdog.

`packages/body/tests/drivers/web/test_dom_extractor.py` (yeni):
- buildDomTree script local HTML'de 5 senaryo (button, link, input, role-button div, aria-label).

`packages/body/tests/drivers/web/test_stagehand_adapter.py` (R4 verify):
- Vendor-test path başarısızsa skipif marker.

#### Acceptance criteria — Order 5
- [ ] PlaywrightWebDriver `start/goto/click/type/screenshot/stop` end-to-end smoke.
- [ ] SecurityWatchdog 6 CVE-2025-47241 case test pass.
- [ ] StorageStateManager save/load + 30sn auto-save watchdog test pass.
- [ ] DOM extractor 5 element type test pass; bbox ve text extraction çalışıyor.
- [ ] Stagehand vendor-test sonucu verify edildi (R4 gate); lokal path OK ise adapter implement, değilse iter et.
- [ ] 5 manuel smoke senaryo (Google search + GitHub PR view + calendar event + OAuth login + form submit) operator'da geçti.

#### Risks — Order 5
- **R4 (ADR-005):** Stagehand vendor-lock. Mitigation: 1-2 gün vendor-test Order 5 başında; başarısızsa custom DOM extraction primary.
- Playwright headless mode bazı sitelerde anti-bot tetikler. Mitigation: M5 default headless=True; per-session opt-out headless=False (operator confirm).
- evaluate() T2 risk; warden gate her invoke'da. Mitigation: dom_extractor pre-approved JS only (allowlist).

---

### Order 6 — Mobile Drivers (Android + iOS sim)

**Hedef:** `packages/body/drivers/{android,ios}/` — Android docker-android+mobile-mcp+uiautomator2 üçlü stack; iOS Simulator-first Appium XCUITest+WDA+go-ios.

**Süre:** 8-10 gün
**Bağımlılık:** Order 1+2+3+4 tamamlandı.

#### Sub-task 6.1 — `packages/body/drivers/android/docker_runtime.py`

```python
class DockerAndroidRuntime:
    """budtmo/docker-android container management."""
    
    def __init__(self, android_version: str = "13.0", device_type: str = "Samsung_Galaxy_S10"):
        self.android_version = android_version
        self.device_type = device_type
        self._container_id: str | None = None
        self._adb_port: int | None = None
    
    async def start(self) -> None:
        # docker run --privileged -d \
        #   -e EMULATOR_DEVICE="<device_type>" \
        #   -e WEB_VNC=true \
        #   -p 4723:4723 -p 6080:6080 -p 5554:5554 -p 5555:5555 \
        #   budtmo/docker-android:emulator_<version>
        cmd = ["docker", "run", "--privileged", "-d",
               "-e", f"EMULATOR_DEVICE={self.device_type}",
               "-e", "WEB_VNC=true",
               "-p", "4723:4723", "-p", "6080:6080", "-p", "5554:5554", "-p", "5555:5555",
               f"budtmo/docker-android:emulator_{self.android_version.replace('.', '_')}"]
        # ...
    
    async def wait_for_boot(self, timeout_sec: int = 120) -> None:
        # adb wait-for-device + getprop sys.boot_completed
    
    async def stop(self) -> None:
        # docker kill + docker rm
```

#### Sub-task 6.2 — `packages/body/drivers/android/mobile_mcp_adapter.py`

```python
import httpx

class MobileMcpAdapter:
    """mobile-mcp HTTP/MCP server wrapper."""
    
    def __init__(self, mcp_url: str = "http://127.0.0.1:8000"):
        self.mcp_url = mcp_url
        self._client = httpx.AsyncClient()
    
    async def tap(self, x: int, y: int) -> None:
        await self._client.post(f"{self.mcp_url}/tap", json={"x": x, "y": y})
    
    async def swipe(self, start_x, start_y, end_x, end_y, duration_ms: int = 250) -> None:
        # ...
    
    async def type_text(self, text: str) -> None: ...
    async def screenshot(self) -> bytes: ...
    async def install_apk(self, path: Path) -> None: ...
    async def app_launch(self, package: str) -> None: ...
    async def press_key(self, key: Literal["back","home","menu","app_switch"]) -> None: ...
    async def dump_a11y_tree(self) -> dict: ...
```

#### Sub-task 6.3 — `packages/body/drivers/android/uiautomator2_fallback.py`

```python
import uiautomator2 as u2

class UiAutomator2Fallback:
    """Pixel-perfect screenshot + low-level fallback."""
    
    def __init__(self, device_serial: str | None = None):
        self.device = u2.connect(device_serial)
    
    async def screenshot_raw(self) -> bytes:
        return self.device.screenshot(format="raw")  # PNG bytes
    
    async def adb_shell(self, command: str) -> str:
        # T2 warden gate (caller responsibility)
        return self.device.shell(command).output
    
    async def install_apk(self, path: Path) -> None:
        # T2 warden gate
        self.device.app_install(str(path))
```

#### Sub-task 6.4 — `packages/body/drivers/android/__init__.py` (UnifiedAndroidDriver)

```python
class AndroidDriver:
    """Unified Android driver: docker runtime + mobile-mcp action + uiautomator2 fallback."""
    
    def __init__(
        self,
        runtime: Literal["docker","physical"] = "docker",
        warden: PermissionWarden = ...,
        vision: VisionOrchestrator | None = None,
    ):
        # ...
    
    async def start(self) -> None:
        if self.runtime == "docker":
            self._runtime_obj = DockerAndroidRuntime()
            await self._runtime_obj.start()
            await self._runtime_obj.wait_for_boot()
        # mobile-mcp + uiautomator2 init
    
    async def click(self, target: str, bbox=None) -> None:
        # Tier-1: a11y tree match → mobile-mcp tap
        # Tier-2: vision fallback → vision_orchestrator.decide() → tap bbox center
        # Tier-3: uiautomator2 raw screenshot → vision call (last resort)
```

#### Sub-task 6.5 — `packages/body/drivers/ios/simulator_runtime.py`

```python
class IosSimulatorRuntime:
    """xcrun simctl management."""
    
    def __init__(self, device_id: str | None = None, ios_version: str = "17.2"):
        self.device_id = device_id
        self.ios_version = ios_version
    
    async def boot(self) -> str:
        # xcrun simctl create / boot / wait-for-boot
        # Returns booted device UDID
    
    async def screenshot(self) -> bytes:
        # xcrun simctl io booted screenshot --type=png /tmp/x.png
        # Read bytes + cleanup
    
    async def shutdown(self) -> None:
        # xcrun simctl shutdown <udid>
    
    async def biometric_match(self) -> None:
        # xcrun simctl ui booted biometric_match enrolled
    
    async def biometric_no_match(self) -> None:
        # xcrun simctl ui booted biometric_no_match
```

#### Sub-task 6.6 — `packages/body/drivers/ios/appium_xcuitest_adapter.py`

```python
from appium import webdriver as appium_webdriver
from appium.options.ios import XCUITestOptions

class AppiumXcuitestAdapter:
    def __init__(self, device_udid: str, appium_url: str = "http://127.0.0.1:4723"):
        opts = XCUITestOptions()
        opts.platform_name = "iOS"
        opts.device_name = device_udid
        opts.automation_name = "XCUITest"
        opts.platform_version = "17.2"
        self._driver = appium_webdriver.Remote(appium_url, options=opts)
    
    async def tap(self, x: int, y: int) -> None: ...
    async def swipe(self, ...) -> None: ...
    async def type_text(self, text: str) -> None: ...
    async def press_key(self, key: str) -> None: ...
    async def app_launch(self, bundle_id: str) -> None: ...
    async def screenshot(self) -> bytes: ...
    async def dump_a11y_tree(self) -> dict: ...
```

#### Sub-task 6.7 — `packages/body/drivers/ios/__init__.py` (UnifiedIosDriver)

Android'le simetrik pattern:

```python
class IosDriver:
    """Unified iOS driver: simulator-first; real device M6+."""
    
    def __init__(
        self,
        runtime: Literal["sim","physical"] = "sim",
        warden: PermissionWarden = ...,
        vision: VisionOrchestrator | None = None,
    ):
        if runtime == "physical":
            raise NotImplementedError("iOS real device M6+; M5 sim-only")
        # ...
```

#### Sub-task 6.8 — Tests

`packages/body/tests/drivers/android/test_docker_runtime.py` (yeni, slow marker):
- Container lifecycle smoke (CI'da skip if no docker; local dev'de full).

`packages/body/tests/drivers/android/test_mobile_mcp_adapter.py` (yeni):
- HTTP wrapper smoke (mocked mobile-mcp server).

`packages/body/tests/drivers/android/test_unified_driver.py` (yeni):
- click/type/screenshot/swipe e2e (docker runtime).

`packages/body/tests/drivers/ios/test_simulator_runtime.py` (yeni, macos-only):
- Boot + screenshot + biometric trigger (mobile-use ios-tests.yml CI workflow paterni).

`packages/body/tests/drivers/ios/test_appium_xcuitest_adapter.py` (yeni, macos-only).

`packages/body/tests/drivers/ios/test_unified_driver.py` (yeni, macos-only):
- 3 senaryo: Safari nav + Settings biometric enroll + Mail send.

#### Acceptance criteria — Order 6
- [ ] DockerAndroidRuntime container start/stop + wait-for-boot.
- [ ] MobileMcpAdapter 8 action surface çalışıyor.
- [ ] UiAutomator2Fallback raw screenshot + adb_shell çalışıyor.
- [ ] AndroidDriver Tier-1/2/3 fallback chain (a11y → vision → raw screenshot).
- [ ] IosSimulatorRuntime boot/screenshot/biometric tam.
- [ ] AppiumXcuitestAdapter 7 action surface çalışıyor.
- [ ] IosDriver simulator-first pattern + physical raises NotImplementedError.
- [ ] 3 Android senaryo (Settings Wi-Fi toggle, Chrome URL nav, APK install) docker container'da geçti.
- [ ] 3 iOS senaryo (Safari nav, Settings biometric enroll, Mail send) Simulator'da geçti.

#### Risks — Order 6
- docker-android container booting Apple Silicon Rosetta'da yavaş olabilir. Mitigation: M5 default Linux x64; macOS arm64 best-effort.
- Appium server süreç yönetimi karmaşık. Mitigation: `appium` subprocess wrapper + auto-start; M5 dev için manual başlatma kabul.
- iOS Simulator camera-dependent app'lar simulator'da yok. M5 scope dışı (cross-app camera senaryoları M6+).

---

### Order 7 — Desktop Drivers (macOS + tmux)

**Hedef:** `packages/body/drivers/desktop/macos/` — PyObjC AX-tree primary + screencapture screenshot fallback + AppleScript runner. `packages/body/drivers/desktop/tmux/` — M3 snapper fleet reuse adapter.

**Süre:** 5-7 gün
**Bağımlılık:** Order 1+2+3+4 tamamlandı.

#### Sub-task 7.1 — `packages/body/drivers/desktop/macos/pyobjc_ax_driver.py`

```python
import objc
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
    AXUIElementPerformAction,
    kAXChildrenAttribute,
    kAXTitleAttribute,
    kAXRoleAttribute,
    kAXPositionAttribute,
    kAXSizeAttribute,
    kAXPressAction,
)

class MacOSAxDriver:
    def __init__(self):
        self._system = AXUIElementCreateSystemWide()
    
    def get_app_element(self, bundle_id: str) -> objc.objc_object | None:
        # NSWorkspace runningApplications → match bundleIdentifier → AXUIElementCreateApplication(pid)
        # ...
    
    def click_element(self, element) -> None:
        AXUIElementPerformAction(element, kAXPressAction)
    
    def get_position(self, element) -> tuple[int, int]:
        err, pos = AXUIElementCopyAttributeValue(element, kAXPositionAttribute, None)
        # CGPoint → (x, y)
    
    def dump_tree(self, root_element) -> dict:
        # Recursive walk via kAXChildrenAttribute
        # Returns {role, title, position, size, children: [...]}
    
    async def click(self, target: str, bbox=None) -> None:
        # Tier-1: AX tree label match → AXPressAction
        # Tier-2: vision fallback → CGEventCreateMouseEvent + post
```

#### Sub-task 7.2 — `packages/body/drivers/desktop/macos/screencapture.py`

```python
class MacOSScreencaptureCapture(ScreenshotCapture):
    """screencapture -x -t png subprocess."""
    
    async def capture(self, rect=None) -> bytes:
        # Already implemented in Order 3.1 generic ScreenshotCapture
        # MacOS-specific: -R rect format "x,y,w,h"
```

#### Sub-task 7.3 — `packages/body/drivers/desktop/macos/applescript_runner.py`

```python
class AppleScriptRunner:
    async def run(self, script: str) -> str:
        # T2 warden gate (caller)
        # osascript -e <script>
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-l", "JavaScript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"AppleScript failed: {stderr.decode()}")
        return stdout.decode()
    
    async def app_launch(self, bundle_id: str) -> None:
        await self.run(f'Application("{bundle_id}").launch();')
    
    async def app_activate(self, bundle_id: str) -> None:
        await self.run(f'Application("{bundle_id}").activate();')
```

#### Sub-task 7.4 — `packages/body/drivers/desktop/macos/__init__.py` (MacOSDesktopDriver)

```python
class MacOSDesktopDriver:
    def __init__(
        self,
        warden: PermissionWarden,
        vision: VisionOrchestrator | None = None,
    ):
        self.warden = warden
        self.vision = vision
        self._ax = MacOSAxDriver()
        self._screencapture = MacOSScreencaptureCapture()
        self._applescript = AppleScriptRunner()
    
    async def click(self, x_or_target: int | str, y: int | None = None, button="left") -> None:
        if isinstance(x_or_target, str):
            # Try AX tree label match first
            elem = self._ax.find_by_label(x_or_target)
            if elem:
                self._ax.click_element(elem)
                return
            # Vision fallback
            if not self.vision:
                raise ValueError("AX label not found and no vision orchestrator")
            screenshot = await self._screencapture.capture()
            decision = await self.vision.decide(screenshot, f"Click on '{x_or_target}'")
            if decision.bbox:
                cx = decision.bbox[0] + decision.bbox[2]//2
                cy = decision.bbox[1] + decision.bbox[3]//2
                self._post_mouse_click(cx, cy, button)
        else:
            self._post_mouse_click(x_or_target, y, button)
    
    def _post_mouse_click(self, x, y, button) -> None:
        # CGEventCreateMouseEvent + CGEventPost
```

#### Sub-task 7.5 — `packages/body/drivers/desktop/tmux/`

M3 snapper fleet (`packages/orchestrator/.../snappers/`) zaten kuruldu. Body driver olarak adapter:

```python
class TmuxDesktopDriver:
    """M3 snapper reuse adapter — body action surface üzerinden tmux send-keys."""
    
    def __init__(self, snapper_root: Path = Path.home() / ".selffork" / "cli-state"):
        self.snapper_root = snapper_root
    
    async def send_keys(self, target_session: str, target_pane: str, keys: str) -> None:
        # tmux send-keys -t <session>:<window>.<pane> <keys>
        # T1 risk_tier (warden gate)
    
    async def capture_pane(self, target_session: str, target_pane: str) -> str:
        # tmux capture-pane -p -t <session>:<window>.<pane>
    
    async def list_sessions(self) -> list[dict]:
        # Read snapper state files
```

#### Sub-task 7.6 — TCC permission gating

`packages/body/drivers/desktop/macos/tcc_check.py`:

```python
async def check_accessibility_permission() -> bool:
    """Check if current process has Accessibility permission."""
    # AXIsProcessTrusted() via PyObjC
    # Returns True if granted

async def check_screen_recording_permission() -> bool:
    # CGRequestScreenCaptureAccess() check
```

Daemon installer post-install script (Order 8):
```sh
echo "SelfFork daemon needs Accessibility + Screen Recording permission."
echo "Open System Preferences → Security & Privacy → Privacy → Accessibility"
echo "Add: /Applications/SelfFork.app (or daemon binary path)"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
```

#### Sub-task 7.7 — Tests

`packages/body/tests/drivers/desktop/macos/test_pyobjc_ax_driver.py` (yeni, macos-only):
- AX system-wide element creation smoke.
- App finder by bundle_id (e.g. "com.apple.finder").
- Tree dump on Finder window.

`packages/body/tests/drivers/desktop/macos/test_applescript_runner.py` (yeni, macos-only):
- `Application("Finder").displayedName` smoke (read-only).

`packages/body/tests/drivers/desktop/macos/test_unified_driver.py` (yeni, macos-only):
- 3 senaryo: Finder file ops + Terminal command + Browser nav.

`packages/body/tests/drivers/desktop/tmux/test_tmux_driver.py` (yeni):
- Mock tmux + snapper state file roundtrip.

#### Acceptance criteria — Order 7
- [ ] MacOSAxDriver app-by-bundle + tree dump + click_element çalışıyor.
- [ ] MacOSScreencaptureCapture rect + full screen modes.
- [ ] AppleScriptRunner app_launch + app_activate; T2 warden gate.
- [ ] MacOSDesktopDriver Tier-1 (AX label) → Tier-2 (vision fallback) chain.
- [ ] TCC check helpers + daemon installer post-install script.
- [ ] TmuxDesktopDriver M3 snapper state read + send-keys.
- [ ] 3 manuel macOS senaryo (Finder file ops + Terminal + Browser) operator'da geçti.

#### Risks — Order 7
- TCC permission UX (CVE-2025-31250 farkındalığı). Mitigation: explicit guide + post-install script.
- atomacos GPL-2.0 contamination YASAK; doğrudan PyObjC + ApplicationServices framework kullanılıyor.
- macOS sandbox-exec dev mode'da Accessibility API'yi bloklayabilir. Mitigation: daemon install profile'da AX whitelist.

---

### Order 8 — Body Daemon (Go cross-platform)

**Hedef:** `packages/body/daemon/` — Go binary, Tailscale ACL, Cockpit Fleet view backend, location-aware slider, macOS/Win/Ubuntu installer'lar. p95 < 2sn round-trip.

**Süre:** 7-10 gün
**Bağımlılık:** Order 1-7 tamamlandı (daemon vision drivers'a değil; daemon ayrı path; ama tmux driver Order 7'den geliyor).

#### Sub-task 8.1 — Go workspace setup

`packages/body/daemon/go.mod`:
```
module github.com/selffork/selffork-daemon

go 1.22

require (
    tailscale.com v1.62.0
    github.com/spf13/cobra v1.8.0
    github.com/google/uuid v1.6.0
    nhooyr.io/websocket v1.8.10
    go.uber.org/zap v1.27.0
)
```

#### Sub-task 8.2 — `packages/body/daemon/cmd/selffork-daemon/main.go`

```go
package main

import (
    "context"
    "github.com/spf13/cobra"
    "selffork-daemon/internal/heartbeat"
    "selffork-daemon/internal/cli_bridge"
    "selffork-daemon/internal/state_reporter"
    "selffork-daemon/internal/command_intake"
)

func main() {
    rootCmd := &cobra.Command{
        Use:   "selffork-daemon",
        Short: "SelfFork body daemon: extends home brain to remote machines via Tailscale",
        RunE:  runDaemon,
    }
    rootCmd.Flags().String("orchestrator-url", "", "Home orchestrator WebSocket URL (Tailscale)")
    rootCmd.Flags().String("machine-id", "", "Daemon machine identifier (auto-derived from hostname if empty)")
    rootCmd.Flags().String("location-tier", "auto", "Location tier: home | work | auto")
    
    if err := rootCmd.Execute(); err != nil {
        log.Fatal(err)
    }
}

func runDaemon(cmd *cobra.Command, args []string) error {
    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()
    
    // 1. Tailscale connect
    // 2. Start heartbeat task
    // 3. Start command intake (WS client)
    // 4. Start state reporter (CLI snapper-style)
    // 5. Wait for SIGINT/SIGTERM
}
```

#### Sub-task 8.3 — `packages/body/daemon/internal/heartbeat/`

```go
package heartbeat

type Heartbeat struct {
    OrchestratorURL string
    MachineID       string
    Interval        time.Duration  // 15s default
    
    backoff time.Duration  // exponential 1s → 2s → 5s → 15s → 30s → 60s
}

func (h *Heartbeat) Run(ctx context.Context) error {
    for {
        select {
        case <-ctx.Done():
            return nil
        case <-time.After(h.Interval):
            if err := h.ping(); err != nil {
                h.backoff = nextBackoff(h.backoff)
                time.Sleep(h.backoff)
            } else {
                h.backoff = 0
            }
        }
    }
}

func (h *Heartbeat) ping() error {
    // POST /api/fleet/heartbeat with {machine_id, version, latency_self_ms, location_tier}
}
```

#### Sub-task 8.4 — `packages/body/daemon/internal/cli_bridge/`

```go
package cli_bridge

type TmuxBridge struct {
    SessionPattern string  // selffork-* prefix filter
}

func (b *TmuxBridge) ListSessions() ([]TmuxSession, error) {
    // tmux list-sessions -F "#{session_name}|#{session_id}|#{session_attached}"
}

func (b *TmuxBridge) SendKeys(session, pane, keys string) error {
    // tmux send-keys -t session:pane keys
}

func (b *TmuxBridge) CapturePane(session, pane string) (string, error) {
    // tmux capture-pane -p -t session:pane
}
```

Windows fallback (PowerShell job control):
```go
type PowerShellBridge struct {}

func (b *PowerShellBridge) ListJobs() ([]PsJob, error) { ... }
func (b *PowerShellBridge) SendInput(jobID, input string) error { ... }
```

#### Sub-task 8.5 — `packages/body/daemon/internal/state_reporter/`

```go
package state_reporter

type Reporter struct {
    OrchestratorURL string
    MachineID       string
    StatePath       string  // ~/.selffork/cli-state/<cli>.json
    Interval        time.Duration  // 1s
}

func (r *Reporter) Run(ctx context.Context) error {
    // Read CLI state files (M3 snapper format)
    // Stream to orchestrator over WS as fleet_status events
}
```

#### Sub-task 8.6 — `packages/body/daemon/internal/command_intake/`

```go
package command_intake

type Intake struct {
    OrchestratorURL string
    MachineID       string
    
    // WS client; receives signed payloads
}

func (i *Intake) Run(ctx context.Context) error {
    // Connect WS → loop receive → decode signed payload → dispatch to local CLI bridge
}

type SignedCommand struct {
    Command   string  // "send_keys" | "capture_pane" | ...
    Args      map[string]any
    Signature string  // HMAC-SHA256 with daemon registration secret
    Nonce     string
    Timestamp time.Time
}
```

#### Sub-task 8.7 — Build matrix (`packages/body/daemon/Makefile`)

```makefile
.PHONY: all macos-arm64 macos-amd64 windows-x64 ubuntu-x64 ubuntu-arm64

VERSION := $(shell git describe --tags --always)
BIN := selffork-daemon

all: macos-arm64 macos-amd64 windows-x64 ubuntu-x64 ubuntu-arm64

macos-arm64:
	GOOS=darwin GOARCH=arm64 go build -o dist/$(BIN)-darwin-arm64 ./cmd/selffork-daemon
	codesign --sign "Developer ID Application: SelfFork" dist/$(BIN)-darwin-arm64
	xcrun notarytool submit dist/$(BIN)-darwin-arm64 --keychain-profile selffork-notary --wait

macos-amd64:
	GOOS=darwin GOARCH=amd64 go build -o dist/$(BIN)-darwin-amd64 ./cmd/selffork-daemon
	codesign --sign "Developer ID Application: SelfFork" dist/$(BIN)-darwin-amd64

windows-x64:
	GOOS=windows GOARCH=amd64 go build -o dist/$(BIN)-windows-amd64.exe ./cmd/selffork-daemon
	# Azure Trusted Signing (M5 sonu opsiyonel; dev unsigned kabul)

ubuntu-x64:
	GOOS=linux GOARCH=amd64 go build -o dist/$(BIN)-linux-amd64 ./cmd/selffork-daemon

ubuntu-arm64:
	GOOS=linux GOARCH=arm64 go build -o dist/$(BIN)-linux-arm64 ./cmd/selffork-daemon

dmg-macos:
	hdiutil create -volname SelfForkDaemon -srcfolder dist/$(BIN)-darwin-arm64 -ov -format UDZO dist/SelfForkDaemon.dmg

deb-ubuntu:
	# fpm -s dir -t deb -n selffork-daemon -v $(VERSION) -a amd64 \
	#   --description "SelfFork body daemon" \
	#   dist/$(BIN)-linux-amd64=/usr/local/bin/selffork-daemon
	@echo "deb packaging via fpm — install fpm via gem install fpm"

msi-windows:
	# WiX toolset
	@echo "msi packaging via WiX — install via choco install wixtoolset"
```

#### Sub-task 8.8 — Installer scripts

`infra/install/macos/install-daemon-macos.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
BREW_TAP="selffork/tap"
brew tap "$BREW_TAP"
brew install selffork-daemon
# TCC permission setup guide
echo "Open System Preferences → Security & Privacy → Privacy → Accessibility"
echo "Add: $(brew --prefix)/bin/selffork-daemon"
launchctl load -w /Library/LaunchDaemons/com.selffork.daemon.plist
```

`infra/install/ubuntu/install-daemon-ubuntu.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update
echo "deb [trusted=yes] https://apt.selffork.dev stable main" | sudo tee /etc/apt/sources.list.d/selffork.list
sudo apt-get update
sudo apt-get install -y selffork-daemon
sudo systemctl enable --now selffork-daemon.service
```

`infra/install/windows/install-daemon-windows.ps1`:
```powershell
Invoke-WebRequest -Uri "https://releases.selffork.dev/v0.5.0/SelfForkDaemon.msi" -OutFile "$env:TEMP\SelfForkDaemon.msi"
msiexec /i "$env:TEMP\SelfForkDaemon.msi" /quiet
sc.exe create SelfForkDaemon binPath= "C:\Program Files\SelfFork\selffork-daemon.exe" start= auto
sc.exe start SelfForkDaemon
```

#### Sub-task 8.9 — Tailscale ACL

`infra/tailscale/acl.json`:
```json
{
  "groups": {
    "group:selffork-orchestrator": ["operator@selffork.dev"],
    "group:selffork-daemon": ["tag:selffork-daemon"]
  },
  "tagOwners": {
    "tag:selffork-daemon": ["group:selffork-orchestrator"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["group:selffork-orchestrator"],
      "dst": ["tag:selffork-daemon:*"]
    }
  ],
  "ssh": [
    {
      "action": "accept",
      "src": ["group:selffork-orchestrator"],
      "dst": ["tag:selffork-daemon"],
      "users": ["root", "operator"]
    }
  ]
}
```

Daemon registration: per-daemon Tailscale auth key (rotated 30 gün); auth key issuance Cockpit "Add Daemon" flow'unda (UI Order 9).

#### Sub-task 8.10 — Backend Fleet API

`packages/orchestrator/src/selffork_orchestrator/dashboard/fleet_router.py` (yeni):
- POST `/api/fleet/heartbeat` — daemon heartbeat ingest.
- POST `/api/fleet/register` — new daemon registration (issue auth key + Tailscale ACL update).
- GET `/api/fleet/daemons` — list registered daemons + status.
- DELETE `/api/fleet/daemons/<id>` — revoke.
- WS `/ws/fleet` — daemon status broadcast.

#### Sub-task 8.11 — Tests

`packages/body/daemon/internal/heartbeat/heartbeat_test.go`:
- Backoff exponential test.
- Reconnect after network drop simulation.

`packages/body/daemon/internal/cli_bridge/tmux_bridge_test.go`:
- Mock tmux subprocess + send-keys/capture-pane round-trip.

`packages/body/daemon/test/integration/round_trip_test.go`:
- Mocked Tailscale + orchestrator stub → daemon → CLI bridge → response.
- p95 < 2sn assertion (stub Tailscale ile latency sentetik).

`packages/orchestrator/tests/dashboard/test_fleet_router.py` (yeni):
- Heartbeat ingest + daemon list + register/revoke flow.

#### Acceptance criteria — Order 8
- [ ] Go binary 5 platform (macOS arm64+amd64, Win x64, Ubuntu x64+arm64) build matrix çalışıyor.
- [ ] Heartbeat exponential backoff + reconnect ≤ 60sn test pass.
- [ ] TmuxBridge send-keys + capture-pane integration test pass.
- [ ] Round-trip integration test (mocked Tailscale) p95 < 2sn.
- [ ] Daemon installer scripts (Homebrew tap, .deb, .msi) draft hazır (M5 sonu manual smoke).
- [ ] Tailscale ACL `infra/tailscale/acl.json` versiyonlanmış; daemon registration Cockpit "Add Daemon" flow'unda hazır (UI Order 9).
- [ ] Fleet API REST + WS endpoint'leri çalışıyor.
- [ ] Unit coverage ≥ %80.
- [ ] Demo: home Mac → work Ubuntu daemon → tmux session spawn → CLI lane → result home cockpit'te.

#### Risks — Order 8
- **R3 (ADR-005):** Cross-platform daemon packaging zorluğu. Mitigation: M5 sonu .msi/.deb manual smoke; release pipeline'a connecting M6 Polish.
- Tailscale auth key rotation otomasyonu yok M5'te. Mitigation: 30 gün manual rotation + cockpit reminder.
- macOS notarize bekleme süresi (Apple notary service) build süresini 5-15 dakika uzatabilir. Mitigation: CI parallelize.

---

### Order 9 — Cockpit + Provider Auth UI

**Hedef:** Cockpit 3 yeni route (Fleet + Providers + Body) + 3 yeni Zustand slice + 4 yeni WS envelope kind + Provider Auth UI 5 provider OAuth orchestration.

**Süre:** 8-10 gün
**Bağımlılık:** Order 1-8 tamamlandı.

#### Sub-task 9.1 — `apps/web/app/cockpit/fleet/page.tsx`

```tsx
"use client";
import { useFleetStore } from "@/lib/store/fleet";
import { useFleetWs } from "@/lib/ws/fleet";

export default function FleetPage() {
  const daemons = useFleetStore(s => s.daemons);
  useFleetWs();  // subscribe to /ws/fleet
  
  return (
    <div className="p-6">
      <h1>Fleet</h1>
      <table>
        <thead>
          <tr>
            <th>Machine ID</th>
            <th>Hostname</th>
            <th>Status</th>
            <th>Latency</th>
            <th>Location Tier</th>
            <th>Last Seen</th>
            <th>Version</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {daemons.map(d => (
            <tr key={d.machine_id}>
              <td>{d.machine_id}</td>
              <td>{d.hostname}</td>
              <td><StatusBadge status={d.status} /></td>
              <td>{d.latency_ms} ms</td>
              <td>{d.location_tier}</td>
              <td>{d.last_seen}</td>
              <td>{d.version}</td>
              <td><DaemonActions daemon={d} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <AddDaemonButton />
    </div>
  );
}
```

#### Sub-task 9.2 — `apps/web/lib/store/fleet.ts`

```ts
import { create } from "zustand";

interface Daemon {
  machine_id: string;
  hostname: string;
  status: "online" | "offline" | "stale";
  latency_ms: number;
  location_tier: "home" | "work";
  last_seen: string;
  version: string;
}

interface FleetState {
  daemons: Daemon[];
  current_machine_id: string | null;
  setDaemons: (daemons: Daemon[]) => void;
  setCurrentMachine: (id: string) => void;
}

export const useFleetStore = create<FleetState>((set) => ({
  daemons: [],
  current_machine_id: null,
  setDaemons: (daemons) => set({ daemons }),
  setCurrentMachine: (id) => set({ current_machine_id: id }),
}));
```

#### Sub-task 9.3 — Location-aware slider

`apps/web/components/cockpit/LocationSlider.tsx`:

```tsx
import { useEffect } from "react";
import { useFleetStore } from "@/lib/store/fleet";
import { useMissionStore } from "@/lib/store/mission";

export function LocationSlider() {
  const currentMachine = useFleetStore(s => s.current_machine_id);
  const daemons = useFleetStore(s => s.daemons);
  const setSliderValue = useMissionStore(s => s.setSliderValue);
  
  useEffect(() => {
    if (!currentMachine) return;
    const daemon = daemons.find(d => d.machine_id === currentMachine);
    if (!daemon) return;
    const value = daemon.location_tier === "home" ? 7 : 4;
    setSliderValue(value);
  }, [currentMachine, daemons]);
  
  return <Slider {...} />;
}
```

#### Sub-task 9.4 — `apps/web/app/cockpit/providers/page.tsx`

```tsx
"use client";
import { useProvidersStore } from "@/lib/store/providers";

const PROVIDERS = ["claude_pro", "codex", "gemini", "opencode", "mmx"] as const;

export default function ProvidersPage() {
  const providers = useProvidersStore(s => s.providers);
  
  return (
    <div className="p-6">
      <h1>Providers</h1>
      {PROVIDERS.map(p => (
        <ProviderCard key={p} name={p} status={providers[p]} />
      ))}
    </div>
  );
}

function ProviderCard({ name, status }) {
  return (
    <div className="border rounded p-4">
      <h2>{name}</h2>
      <StatusBadge status={status?.connected ? "connected" : "disconnected"} />
      {status?.expires_at && <ExpiryGauge expires_at={status.expires_at} />}
      <div className="mt-2 space-x-2">
        <Button onClick={() => signInWithBrowser(name)}>Sign in with browser</Button>
        <Button onClick={() => refreshToken(name)} disabled={!status?.connected}>Refresh</Button>
        <Button onClick={() => disconnect(name)} variant="destructive" disabled={!status?.connected}>Disconnect</Button>
      </div>
      {name === "claude_pro" && <ToSWarningBanner />}
    </div>
  );
}
```

#### Sub-task 9.5 — `signInWithBrowser` orchestration

`apps/web/lib/providers/sign_in.ts`:

```ts
export async function signInWithBrowser(provider: string) {
  // POST /api/providers/<name>/sign_in_start
  // → backend launches body web driver in headless=False mode
  // → opens provider OAuth URL
  // → operator manually completes login
  // → callback intercepted at localhost:6XXXX
  // → storage_state saved
  const response = await fetch(`/api/providers/${provider}/sign_in_start`, {method: "POST"});
  const {session_id} = await response.json();
  
  // Subscribe to WS for status updates
  const ws = new WebSocket(`/ws/providers/${session_id}`);
  ws.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    if (event.type === "provider.auth.success") {
      toast.success(`${provider} connected!`);
    } else if (event.type === "provider.auth.failed") {
      toast.error(`${provider} sign-in failed: ${event.reason}`);
    }
  };
}
```

Backend: `packages/orchestrator/src/selffork_orchestrator/dashboard/provider_router.py` (yeni):
- POST `/api/providers/<name>/sign_in_start` — launch body web driver, return session_id.
- POST `/api/providers/<name>/refresh` — provider-specific refresh.
- POST `/api/providers/<name>/disconnect` — token revoke + storage_state delete.
- GET `/api/providers` — read all provider statuses (storage_state file presence + expiry).
- WS `/ws/providers/<session_id>` — auth flow status stream.

Provider-specific orchestrators (`packages/orchestrator/.../auth/`):
- `claude_pro_auth.py` — opt-in only + ToS warning + browser-driven; M5 default DISABLED.
- `codex_auth.py` — RFC 8628 device-code flow.
- `gemini_auth.py` — browser-callback + localhost intercept (`~/.gemini/oauth_creds.json` write).
- `opencode_auth.py` — API key paste form.
- `mmx_auth.py` — API key paste form.

#### Sub-task 9.6 — `apps/web/app/cockpit/body/page.tsx`

```tsx
"use client";
import { useBodyStore } from "@/lib/store/body";

export default function BodyPage() {
  const sessions = useBodyStore(s => s.sessions);
  const events = useBodyStore(s => s.events);  // last 100 body.* audit events
  
  return (
    <div className="p-6 grid grid-cols-2 gap-6">
      <div>
        <h2>Active Sessions</h2>
        {sessions.map(s => (
          <SessionCard key={s.session_id} session={s} />
        ))}
      </div>
      <div>
        <h2>Action Stream</h2>
        <BodyActionStream events={events} />
      </div>
      <div>
        <h2>Screenshot Timeline</h2>
        <ScreenshotTimeline events={events.filter(e => e.category === "body.observation")} />
      </div>
      <div>
        <h2>Vision Latency</h2>
        <LatencyGauge events={events.filter(e => e.category === "body.vision.query")} />
      </div>
    </div>
  );
}
```

#### Sub-task 9.7 — WS envelope kind extension

`packages/orchestrator/src/selffork_orchestrator/dashboard/ws_protocol.py`:

```python
class WsEnvelopeKind(Enum):
    # ... existing M4 kinds ...
    FLEET_STATUS = "fleet_status"
    BODY_ACTION = "body_action"
    BODY_OBSERVATION = "body_observation"
    PROVIDER_AUTH_STATUS = "provider_auth_status"
```

`apps/web/lib/ws/types.ts`:
```ts
export type WsEnvelope =
  | {kind: "fleet_status", payload: Daemon}
  | {kind: "body_action", payload: BodyActionEvent}
  | {kind: "body_observation", payload: BodyObservationEvent}
  | {kind: "provider_auth_status", payload: ProviderAuthEvent}
  | ... // existing M4 kinds
```

#### Sub-task 9.8 — Body Stop button + Permission Approval UI

`apps/web/components/body/StopButton.tsx`:
```tsx
export function StopButton({sessionId}) {
  return (
    <Button
      variant="destructive"
      onClick={async () => {
        await fetch(`/api/body/sessions/${sessionId}/stop`, {method: "POST"});
        toast.success("Session stopped");
      }}
    >
      Stop
    </Button>
  );
}
```

`apps/web/components/body/PermissionApprovalModal.tsx`:
```tsx
export function PermissionApprovalModal({request, onApprove, onDeny}) {
  return (
    <Dialog open>
      <DialogContent>
        <h2>Action Approval Required</h2>
        <p>Action: {request.action_type}</p>
        <p>Risk Tier: {request.risk_tier}</p>
        <p>Target: {request.target_uri_redacted}</p>
        <pre>{JSON.stringify(request.args_summary, null, 2)}</pre>
        <DialogFooter>
          <Button variant="default" onClick={onApprove}>Approve</Button>
          <Button variant="destructive" onClick={onDeny}>Deny</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

#### Sub-task 9.9 — Tests

`apps/web/__tests__/cockpit/fleet.test.tsx` (yeni, vitest):
- FleetPage render + daemon list.
- LocationSlider auto-shift on machine change.

`apps/web/__tests__/cockpit/providers.test.tsx` (yeni):
- ProviderCard render her status için.
- signInWithBrowser flow stub.

`apps/web/__tests__/cockpit/body.test.tsx` (yeni):
- BodyPage render + event stream + screenshot timeline.
- StopButton click → POST request.

`packages/orchestrator/tests/dashboard/test_fleet_router.py`: Order 8 ile birlikte.

`packages/orchestrator/tests/dashboard/test_provider_router.py` (yeni):
- 5 provider sign-in flow stub + status read.

#### Acceptance criteria — Order 9
- [ ] Cockpit `/fleet` route render + WS canlı + 3 daemon stub.
- [ ] LocationSlider auto-shift home=7 ↔ work=4 (machine change'e tepki).
- [ ] Cockpit `/providers` route render + 5 provider card.
- [ ] "Sign in with browser" flow 3 senaryo (codex device-code + gemini browser-callback + opencode form paste) end-to-end smoke.
- [ ] Cockpit `/body` route render + active session + action stream + screenshot timeline + latency gauge.
- [ ] Stop button + Permission approval modal canlı.
- [ ] Frontend test ≥ 130 toplam (M4 baseline 83 üstünde + ≥ 47 yeni).
- [ ] Backend Provider router 5 endpoint test pass.
- [ ] Manual smoke: 3 daemon + 3 provider sign-in + 1 body session full lifecycle.

#### Risks — Order 9
- Provider OAuth browser-driven flow per-provider farklılıkları (CAPTCHA, MFA). Mitigation: M5 Phase 1 manual login (operator browser pencerede tıklıyor); Phase 2 otomatize sadece self-account.
- Claude Pro automation ToS riski. Mitigation: opt-in only + ToS warning banner + default disabled.
- `/body` route screenshot timeline image rendering performance. Mitigation: lazy load + thumbnail cache.

---

## 5. Cross-cutting concerns

### 5.1 Performance budget

| Path | Budget | Method |
|---|---|---|
| Daemon round-trip (Tailscale) | p95 < 2s | mocked Tailscale integration test |
| Vision call (screenshot→action) | p95 < 2s | held-out 30-task eval |
| Action precision | ≥ 85% | held-out 30-task eval |
| Cockpit Fleet WS update | < 500ms | manual smoke |
| Permission warden decision | < 100ms (auto modes) | unit test |
| Audit emit JSONL latency | < 50ms | unit test |

### 5.2 Test budget per Order

| Order | Backend tests added | Frontend tests added |
|---|---|---|
| 1 | ~20 (audit + redaction + chatmessage + storage) | 0 |
| 2 | ~30 (warden + watchdog + sandbox backends) | 0 |
| 3 | ~25 (vision pipeline + 30-task eval harness) | 0 |
| 4 | ~30 (10 body.* tools + jr autopilot integration) | 0 |
| 5 | ~30 (web driver + watchdog + storage_state + dom_extractor) | 0 |
| 6 | ~40 (android docker + mobile-mcp + uiautomator2 + ios sim + appium) | 0 |
| 7 | ~25 (macos AX + screencapture + applescript + tmux) | 0 |
| 8 | ~35 Go (heartbeat + cli_bridge + state_reporter + intake) + ~20 Python (fleet router) | 0 |
| 9 | ~20 (provider router + body router) | ~50 (cockpit fleet + providers + body) |
| **Total** | **~275** | **~50** |

Hedef: 1248 + 275 = ~1523 backend (≥ 1500), 83 + 50 = 133 frontend (≥ 130).

### 5.3 Audit category coverage

Her Order'ın acceptance criteria audit emit'i şart koşar:

| Category | Order |
|---|---|
| body.driver.start/stop | 5,6,7 |
| body.action.invoke/executed/failed | 4,5,6,7 |
| body.permission.requested/deny | 2 |
| body.vision.query | 3 |
| body.observation | 3 |
| provider.auth.requested/success/failed | 9 |
| provider.token.refreshed/expired | 9 |

### 5.4 ROADMAP.md revize PR (M5 close-out'ta)

`docs/ROADMAP.md` 3 bölüm güncellenir:

1. **§7 Driver Roadmap (Body)** — vision drivers tier'ları ADR-005 §"Eski karar" tablosuyla revize.
2. **§M5 Body Daemon (line 576)** — scope expansion (daemon + vision drivers + sandbox/warden + provider auth ui), 6-8 hafta.
3. **§0 Roadmap at a Glance** + **§3 Critical Path & Parallelization** — M5 süre tablosu güncelleme (3 wk → 6-8 wk; 2026-09 → 2026-10).

ROADMAP revize PR audit-god review pass'inden sonra atılır (operator commit).

### 5.5 ADR-005 close-out (M5 done)

ADR-004 paterni:
- §Final test/lint durumu (gerçek) — backend/frontend test sayısı + ruff/mypy clean status.
- §Manuel smoke checklist (operator laptop) — 9 senaryo (3 driver + 3 provider sign-in + 1 daemon round-trip + 1 vision eval + 1 cockpit full).
- §Audit-fix wave — 9 paralel audit-god ajanı bulguları + P0/HIGH kapatıldı.
- §Sınırlamalar / kalan iş (M6+'a iter — confirmed) — implementasyondan derlenen yeni iter list.
- §Sources (close-out — gerçek artefakt referansları).

### 5.6 Documentation outputs (M5 close-out)

- `docs/architecture/body-daemon-protocol.md` — daemon ↔ orchestrator wire format + signing.
- `docs/architecture/body-vision-pipeline.md` — Tier-1/2/3 + token budget + latency budget.
- `docs/architecture/body-permission-warden.md` — 3-mod x 4-tier matrix + state machine.
- `docs/operations/install-daemon-{macos,windows,ubuntu}.md`.
- `docs/operations/provider-auth-ui-guide.md` — 5 provider per-flow.
- `docs/research/M5_korpus.md` — 16 ajan ARGE özet (ADR-005 §Sources'tan derlenir).

---

## 6. Done definition (M5 milestone done)

M5 ancak şunlar **hepsi** geçtiğinde "done":

### Daemon Layer
- [ ] Daemon Tailscale round-trip p95 < 2sn (mocked + manual smoke).
- [ ] 3 platform installer (Homebrew tap, .deb, .msi) çalışıyor.
- [ ] Cockpit Fleet view 3 daemon stub'la canlı; location-aware slider auto-shift verify.
- [ ] Demo: home Mac → work Ubuntu daemon → CLI lane spawn → result.

### Vision + Drivers
- [ ] 30-task held-out vision eval ≥ %85 action precision (R1 gate).
- [ ] Web driver: 5 senaryo manual smoke geçti.
- [ ] Android driver: 3 senaryo (docker container).
- [ ] iOS sim driver: 3 senaryo.
- [ ] macOS desktop driver: 3 senaryo (AX + vision fallback).
- [ ] Tmux desktop driver (M3 reuse): 5 CLI canlı, regression-free.

### Sandbox + Warden + Audit
- [ ] PermissionWarden 3-mod x 4-tier 12-case test pass.
- [ ] CVE-2025-47241 mitigation 6-case test pass.
- [ ] BodyWatchdog SIGKILL container'a (agent'a değil).
- [ ] 14 yeni AuditCategory + opsiyonel payload alanları emit.
- [ ] Screenshot persistence path; binary inline YOK; redaction katmanı çalışıyor.
- [ ] macOS sandbox-exec + Linux bubblewrap dev-mode smoke.

### Provider Auth UI
- [ ] Cockpit `/providers` 5 provider read-only status surface.
- [ ] 3 provider sign-in flow (codex device-code + gemini browser-callback + opencode form paste) end-to-end.
- [ ] storage_state per provider kaydediliyor.
- [ ] 5 yeni `provider.*` AuditCategory emit.

### Tests + Lint + Manuel Smoke
- [ ] Backend test ≥ 1500 (M4 baseline 1248 + ≥ 252).
- [ ] Frontend test ≥ 130 (M4 baseline 83 + ≥ 47).
- [ ] Go daemon unit ≥ %80 + 1 e2e mocked Tailscale.
- [ ] `ruff` Body pillar dosyaları clean; mevcut S108 7 baseline kapatıldı.
- [ ] `mypy --strict` Body pillar (Python kısmı) success.
- [ ] M3+M4 baseline regression-free (1331 mevcut test pass).
- [ ] 9-senaryo manual smoke (operator laptop) geçti.

### Audit-fix wave
- [ ] 9 paralel audit-god ajanı.
- [ ] P0/HIGH bulgular kapatıldı.

### Documentation
- [ ] 6 doc çıktısı eklendi (3 architecture + 3 operations + 1 research).
- [ ] ADR-005 close-out bölümleri (Final test/lint, Manuel smoke, Audit-fix wave, Sınırlamalar, Sources) dolduruldu.

### ROADMAP revize
- [ ] §7 + §M5 + §0 + §3 revize PR atıldı (operator commit).

---

## 7. Sources

### ADR + ROADMAP
- [`docs/decisions/ADR-005_M5_Body.md`](../decisions/ADR-005_M5_Body.md) — bu plan'ın referans karar belgesi (ACCEPTED 2026-05-10).
- [`docs/decisions/ADR-001_MVP_v0.md`](../decisions/ADR-001_MVP_v0.md) §4 + §14.9 — packages/body skeleton mandate.
- [`docs/decisions/ADR-002_Mind_Architecture.md`](../decisions/ADR-002_Mind_Architecture.md) — Mind T1-T6 + GraphRAG.
- [`docs/decisions/ADR-003_M3_CLI_Surfing.md`](../decisions/ADR-003_M3_CLI_Surfing.md) — 6 CLI snapper + Jr autopilot 11-tool.
- [`docs/decisions/ADR-004_M4_Cockpit.md`](../decisions/ADR-004_M4_Cockpit.md) — M-1 WS protocol + 4-tab cockpit + 28-cat audit.
- [`docs/ROADMAP.md`](../ROADMAP.md) §0/§3/§7/§M5 — revize bekliyor.
- [`docs/Yamac_Jr_Nano_Kararlar.md`](../Yamac_Jr_Nano_Kararlar.md) — base model + context + fine-tune SSoT.

### M4 plan paterni (mirror)
- [`docs/plans/M4_Cockpit_Plan.md`](./M4_Cockpit_Plan.md) — 9-order template.

### 16 ajan ARGE (2026-05-10)
ADR-005 §Sources bölümünde tam liste; özet plan'da sub-task'lerde inline referans.

### Korpus referansları (MANDATE 9)
- `examples_crucial/browser-use/` — Apache 2.0, Order 5 web driver primary referans.
- `examples_crucial/Skyvern-AI/skyvern/` — AGPL-3.0 ⚠️, Order 5 sadece pattern referansı.
- `examples_crucial/minitap-ai/mobile-use/` — Apache 2.0, Order 6 mobile birebir referans.
- `examples_crucial/felixrieseberg/clippy/` — MIT, Order 7 desktop building block.

### External docs
- HF blog gemma4 — Gemma 4 vision capability.
- ai.google.dev/gemma/docs/capabilities/vision — Gemma 4 vision-language.
- Anthropic Computer Use docs (platform.claude.com).
- OpenAI Codex sandbox docs (developers.openai.com/codex/).
- AndroidWorld google-research.github.io.
- Apple Developer / WebDriverAgent / xcrun simctl docs.
- Tailscale ACL docs (tailscale.com/kb/1018/acls).
- Playwright docs (playwright.dev).

---

**Implementation başlama:** Order 0 pre-flight checklist verify → Order 1.
