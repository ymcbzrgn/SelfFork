# ADR-003 — M3 CLI Surfing

> **⚠ Partial supersession — ADR-006 (2026-05-17 v3 pivot).**
> The router-strategy section (rotation-based selection) is replaced
> by [`ADR-006_v2_Pivot.md`](./ADR-006_v2_Pivot.md) §4.6 — three
> input signals (quota remaining + operator override + RAG project–CLI
> affinity). The CLI fleet expansion (claude / codex / gemini / minimax
> / glm) and the Surfer machinery in this document remain in effect.

**Tarih:** 2026-05-09
**Durum:** Kabul edildi (uygulamada)
**Bağlam:** `docs/ROADMAP.md` §M3, ARGE 2026-05-09 (10 paralel ajan + 9 order plan)

## Karar

M3 milestone'u 9 order'a bölünmüş şekilde uygulanır. Her order kendi içinde
production-quality (memory: `feedback_no_mvp_full_quality_first_time`):
pluggable interface day 1, eval coverage day 1, plain-md projection day 1.

| # | Order | Kapsam | Durum |
|---|-------|--------|-------|
| 1 | Proactive Quota Layer | Snapper foundation (quota.py + 5 snapper + runner + factory + ProactiveUsageReader) | ✅ |
| 2 | CodexAgent + codex_detector | Stub'tan production impl + rate-limit detector | ✅ |
| 3 | Cron-sleep launchd | macOS plist generator + install/uninstall | ✅ |
| 4 | Jr Autopilot Tool Surface | 11-tool registry (4 read / 5 act / 2 reflect) | ✅ |
| 5 | Telegram Bridge | ABC + Null + AllowList + Inbox SQLite (PTB Order 9) | ✅ |
| 6 | Cross-CLI Context Handoff | HandoffBundle Pydantic + Store (Letta `.af` esinli) | ✅ |
| 7 | Minimax mmx-cli | MinimaxCliAgent + detector + snapper (Token Plan) | ✅ |
| 8 | Z.AI / GLM | ZaiSnapper (opencode-routed, OAuth-only) | ✅ |
| 9 | E2E + Polish | Integration tests + ADR + cli.py wire + audit-fix (12) + close-out (7) | ✅ |

## Mimari kararlar

### M-1: Auth-only zorunluluk (operator directive 2026-05-09)

**API key ASLA kullanılmaz.** Sadece subscription OAuth.
- **Claude Pro** → `claude` CLI (statusline.sh stdin JSON)
- **ChatGPT Plus** → `codex` CLI (rollout JSONL TokenCountEvent)
- **Google Code Assist OAuth** → `gemini` CLI (telemetry log + `/stats model`)
- **Minimax subscription** → `mmx` CLI (Token Plan API)
- **Z.AI Coding Plan** → opencode auth login native OAuth

ZaiSnapper'da bile `type: "api"` reddedilir; sadece `type: "oauth"` kabul.

### M-2: Cross-CLI proactive quota layer

Her CLI için ayrı snapper (`packages/orchestrator/.../snappers/<cli>.py`):
- Sinyal kaynağı: statusline JSON (Claude), rollout JSONL (Codex),
  telemetry log (Gemini), SQLite (opencode), credentials.json (mmx, zai)
- Output: normalized `QuotaSnapshot` Pydantic (windows + context)
- Disk: `~/.selffork/cli-state/<cli_id>.json` (atomic tempfile + os.replace)
- Cadence: 1sn (Claude statusline ritmine eşlenir)
- Reader: `ProactiveUsageReader.read(cli_id)` — stale_after_seconds=300 default

Audit log layer (UsageAggregator) **kaldırılmadı** — proactive snapshot eski
audit-log derivation'a (memory: `project_provider_usage_source`) **ek**, fallback.

### M-3: Jr autopilot tool surface (11 tool)

Operator directive: "rotation falan da model kendi karar versin, fine-tune
sonrası karar vermeyi öğrenecek."

Endüstri konsensüsü ile uyumlu (Anthropic Computer Use, OpenAI Agents SDK,
LangGraph `Command`): **tool call as decision verb**. Hardcoded routing OUT.

**4 read** (`quota_snapshot`, `available_clis`, `session_state`, `mind_recall`)
**5 act** (`rotate_to`, `sleep_until`, `notify_telegram`, `compact_context`, `mark_done`)
**2 reflect** (`mind_note_add`, `cancel_pending`)

BiasBusters paper (ICLR 2026, arxiv:2510.00307): ≥20 tool'da positional bias
patlıyor — 11 güvenli aralık.

### M-4: Cron-sleep launchd

macOS-only Order 3. `cron(8)` deprecated; `launchd StartCalendarInterval`
laptop uykudan kalkar kalkmaz tetiklenir — quota reset semantiği için kritik.

Linux/Windows scheduler M5+'a iter.

### M-5: Telegram bridge ABC pattern

Order 5 scaffold: `TelegramBridge` ABC + `NullTelegramBridge` (M3-M5
default). Order 9'da PTB v22.7 wire. AllowList JSON (`~/.selffork/operators.json`)
+ `TelegramInbox` SQLite (sleep_until döneminde mesaj queue).

ABC pattern sayesinde Jr autopilot'un `notify_telegram` tool'u PTB
yokken bile audit log'a düşer — M7 fine-tune dataset için operator-style
notify kararları korunur.

### M-6: Cross-CLI handoff (Letta `.af` esinli)

`HandoffBundle` Pydantic schema:
- `active_task` (PRD restated)
- `transcript_recent` (last N rounds)
- `transcript_digest` (LLM özet)
- `memory_subset` (Mind tier referansları — payload duplication YOK)
- `tool_state` (cwd + env_whitelist + open_files)

`env_whitelist` allow-list — secrets ASLA travel etmez (her CLI kendi
auth'unu kullanır).

### M-7: Fine-tune felsefesi (M7 önceki tüm infra hazır)

Operator directive (memory: `feedback_infra_before_finetune`):
- M3-M6 boyunca tool surface + state injection + rich audit logs
- M7 SFT dataset = M3-M6 audit log + operator approval signals
- Adapter system usage + operator reflexes tek seferde öğrenir
- M7+ system prompt minimal (sadece tool listesi)

Aynı 11-tool surface M3-M6 (base model + explicit playbook) ve M7+ (adapter
+ minimal prompt) dönemlerinde — sadece system prompt swap.

## Sınırlamalar / kalan iş

**Order 9 close-out tamamlandı (2026-05-09 16:30 GMT+3):**

- ✅ `cli.py` round-loop wire — Session constructor `proactive_reader`/`launchd_scheduler`/`resume_store`/`telegram_bridge` parametreleri + `SnapperRunner` background anyio task (T17)
- ✅ PTB v22.7 concrete `PtbTelegramBridge` — `SELFFORK_TELEGRAM_BOT_TOKEN` env-aware factory + Null fallback (T18)
- ✅ Z.AI `/v1/usage` HTTP probe — `ZaiSnapper` httpx + `rate_limit_5h`/`rate_limit_daily` projection (T15)
- ✅ Minimax Token Plan `/v1/token_plan/remains` HTTP probe — `MinimaxSnapper` httpx + Bearer OAuth (T16)
- ✅ `mark_done` sentinel propagation — Jr autopilot `mark_done` tool çağrısı round-loop'u DONE'a çeker (T13)
- ✅ Audit attribution — `mmx` binary → `minimax-cli` mapping (audit_reader + aggregator, T1 audit-fix)
- ✅ `rotate_to(zai)` reject — snapper-only provider'lar rotate target olamaz (T2 audit-fix)
- ✅ HandoffBundle path-traversal guard + `env_whitelist` secret denylist + dead validator removal (T3+T4+T10 audit-fix)
- ✅ launchd Year-recur orphan + `sleep_until` empty-prd_path crash (T7+T8 audit-fix)
- ✅ Codex/Claude context-token sum'ı + cached double-count (T5+T6 audit-fix)
- ✅ ADR brand violation (T11 audit-fix)
- ✅ codex_detector auth false-positive tighten (T12 audit-fix)
- ✅ Empty-windows snapshot → `available_clis` `auth_only` status (T9 audit-fix)

**M4+ scope'a iter (intentional defer):**

- Mind compaction integration — `compact_context` tool gerçek compactor çağrısı için `MindStore.list_recent` API gerek (Mind paketinde yeni method); şimdilik intent-record stub
- Telegram inbound command handling — `/cancel`, `/p <slug> <msg>` yönü; outbound notify v22.7'de canlı
- Linux/Windows scheduler — `LaunchdScheduler` alternatifi (systemd user timer + Windows Task Scheduler); macOS-only günümüzde
- mmx CLI surface manuel verify — Yamaç laptop'una `npm i -g @minimaxai/cli` + `mmx --help` çıktısıyla `chat -p` flag'leri doğrulanmalı (Order 7 audit MEDIUM-confidence iddiaları)
- Codex CLI surface manuel verify — `codex exec --resume-last` flag doğrulaması (Order 2 audit CRITICAL-confidence-MEDIUM iddiası)

## Eski karar (varsa)

ADR-001 §5.3 round-loop tasarımı korunur — autopilot Yamaç Jr'ın round
döngüsünün **içinde** karar verir, dışında değil.

ADR-002 Mind 6-tier mimarisi korunur — autopilot Mind'a `mind_recall` /
`mind_note_add` ile bağlı, ayrı bir memory katmanı yok.

## Etki

- **Pillar 1 (Reflex):** M7 SFT dataset için M3-M6 audit log standardı sabit
- **Pillar 2 (Body):** etkilenmez (M5'e iter)
- **Pillar 3 (Mind):** autopilot tool'ları Mind retriever/writer'ı consume eder; yeni katman yok

## Kabul kriterleri (M3 done)

- [x] 9 order test coverage (619 baseline → 752 final, +133 yeni test)
- [x] Cross-pillar e2e integration test (`test_m3_e2e_integration.py`)
- [x] ADR yazıldı (bu dosya)
- [x] cli.py round-loop integration (T17 — Session + SnapperRunner + ToolContext wire)
- [x] PTB v22.7 wiring (T18 — env-token-aware factory; ntfy fallback M4'e iter)
- [x] 12 audit-fix CRITICAL/HIGH bulgu kapatıldı (9 audit-god ajanı raporları)
- [x] Order 9 close-out (T13-T19: 7 sub-task)
- [ ] Operator manual run smoke test — Yamaç tarafında PRD ile ilk gerçek koşu

## Final test/lint durumu (2026-05-09 16:30 GMT+3)

- **752 test pass** (orchestrator: 752 + mind: 292 + shared: 91 = repo-wide 1135)
- **ruff** — All checks passed (production code temiz)
- **mypy strict** — 99 source file, no issues

## Sonraki M3 işleri (Order 9 close-out)

1. Full regression çalıştır (619 + Order 5-8 yeni testler)
2. ruff + mypy temiz mi kontrol
3. cli.py round-loop driver: autopilot tool sinyallerini gözle
4. PTB v22.7 dependency + bridge concrete impl
5. M3 demo PRD: 4 CLI rotate eden bir senaryo

## Sources

- ARGE 2026-05-09: 10 paralel selffork-researcher + explorer-god ajanı (kanıt-temelli mimari kararlar)
- BiasBusters paper: arxiv:2510.00307 (ICLR 2026)
- PersonaAgent paper: arxiv:2506.06254
- Letta `.af` AgentFileSchema: examples_crucial/letta/letta/schemas/agent_file.py
- Codex CLI rollout JSONL: github.com/openai/codex (DeepWiki 4.4)
- Anthropic statusline schema: code.claude.com/docs/en/statusline (v2.1.80+)
- mmx-cli: github.com/MiniMax-AI/cli
- Z.AI Coding Plan: docs.z.ai/scenario-example/develop-tools/opencode
