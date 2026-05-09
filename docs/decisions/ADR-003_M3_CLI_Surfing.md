# ADR-003 — M3 CLI Surfing

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
| 9 | E2E + Polish | Integration tests + ADR + cli.py wire (kısmi) | ⏳ |

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

## Sınırlamalar / kalan iş (Order 9'a iter)

- `cli.py` round-loop driver henüz autopilot tool sinyallerini consume etmiyor
- PTB v22.7 implementation (Telegram bridge gerçek HTTP)
- Z.AI `/v1/usage` HTTP probe (ZaiSnapper full implementation)
- Minimax Token Plan `/v1/token_plan/remains` HTTP probe (MinimaxSnapper)
- Mind compaction integration (autopilot `compact_context` → real compactor)
- Linux/Windows scheduler (launchd alternatifi)

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

- [x] 9 order test coverage (719+ test M3 öncesi → 770+ M3 sonu beklenen)
- [x] Cross-pillar e2e integration test (`test_m3_e2e_integration.py`)
- [x] ADR yazıldı (bu dosya)
- [ ] cli.py round-loop integration (Order 9 sonrası)
- [ ] Operator manual run smoke test (Order 9 sonrası)
- [ ] PTB v22.7 + ntfy fallback wiring (Order 9 sonrası)

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
