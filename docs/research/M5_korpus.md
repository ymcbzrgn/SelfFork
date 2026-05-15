# M5 Body — Crucial Corpus Distillation (2026-05-15)

> 21 + 11 = 32 toplam crucial repo. M5 implementation süresince 16 ARGE ajanı + audit-fix wave'de 9 audit-god + 10 explorer-god ajan kullanıldı. Bu dosya **distilled findings** — tüm ajan raporlarının pillar-bazlı sentezi.

## §1 — M5 Body pillar (kritik 5 repo)

### UI-TARS-desktop (bytedance, Apache-2.0)
- **Mimari:** pnpm monorepo; Electron desktop GUI + multimodal/agent-tars CLI/SDK/Web
- **Operator pattern:** `Operator` abstract → `screenshot()` + `execute(action)`. browser-operator (Playwright via CDP) + nut-js (cross-platform desktop) + adb (Android)
- **Vision:** OpenAI-compatible model çağrısı (Volcano doubao-seed-1.6). **SoM/ROI fallback yok.**
- **AGIO telemetry** — Cockpit Fleet view için event schema referans
- **Bizden farklar:** frontier-model-dependent (R1 felsefemize ters); permission warden YOK; cross-platform daemon (Go) YOK
- **Direkt alınabilir:** CDP-based screenshot path (`local-browser-operator.ts:108-145`); nut-js Win/Linux input layer (M6+); AGIO event schema

### cua (trycua, MIT) — **EN DEĞERLİ M5+/M6 referans**
- **Mimari:** Python + Swift (Lume macOS Virtualization.framework) + Docker (Lumier); 6 paket monorepo
- **Sandbox = full VM:** 4 provider — `LUME` (macOS native VM), `CLOUD` (cua-hosted), `LUMIER` (Docker), `WINSANDBOX` (Windows Sandbox). `BaseComputerProvider` ABC pattern
- **Cross-platform adapter:** `InterfaceFactory.create_interface_for_os()` `macos|linux|windows` string-based dispatch
- **SDK:** `ComputerAgent(model="anthropic/...", tools=[computer], max_trajectory_budget=...)` LiteLLM-uyumlu çoklu model
- **EVAL HARNESS VAR** — HUD platform entegrasyonu `run_full_dataset(dataset="hud-evals/OSWorld-Verified", agent_config={...}, max_concurrent, max_steps)` (`agent/integrations/hud/eval.py:1-80`)
- **Direkt alınabilir (M6):** Eval harness shape (HUD shape adopt, transport biz yaz); BaseComputerProvider VM abstraction; OS-string interface factory pattern

### CloakBrowser (CloakHQ, MIT wrapper + proprietary binary)
- **Mimari:** Playwright pure wrapper — döndürdüğü standart Playwright `Browser` object; binary executable_path swap
- **Source-level patches:** 57 fingerprint patches Chromium C++ kaynakta compiled (binary download ~200MB)
- **Test suite:** reCAPTCHA v3 (0.9 score), Cloudflare Turnstile, ShieldSquare, FingerprintJS, bot.incolumitas
- **Direkt alınabilir:** `playwright_driver.py:71` `chromium.launch(executable_path=cloak_binary, args=stealth_args)` swap pattern; `IGNORE_DEFAULT_ARGS=['--enable-automation']` bedavaya gelen iyileştirme
- **R4 yerine geçmez** — Stagehand AI-action primitive (act/extract/observe); CloakBrowser stealth-only
- **Legality:** CloakBrowser kendi BINARY-LICENSE'ında credential stuffing/brute-force/automated account YASAK; SelfFork "ToS-friendly self-account" constraint korunur

### financial-services (anthropics, MIT)
- **Mimari:** Claude Code skill suite — 18 skill (`SKILL.md` YAML frontmatter) + 15 subagent (`.claude/agents/*.md`)
- **SIFIR Python kodu** — pure prompt + skill markdown. Computer-use değil
- **Direkt alınabilir:** Skill formatı (YAML frontmatter `name/description/when_to_use/decision_tree`); subagent frontmatter `tools` allow-list
- **ADR-006 Skill Packs adayı için temel kaynak**

### video-search-and-summarization (NVIDIA, Apache-2.0)
- **Mimari:** README-only (sığ checkout). NVIDIA NIM microservice + Docker Compose + Brev Launchable (cloud)
- **Vision:** Cosmos-Reason2-8B (VLM) + Nemotron-Nano-9B-v2 (LLM) NVIDIA AI Enterprise license gerekli
- **Pipeline:** 3 katman (real-time intelligence → analytics → MCP agentic search)
- **M5 etkisi:** YOK (single-host Mac Silicon hedefi); M6 rented GPU server için microservice serving pattern referans
- **Reddet:** NVIDIA AI Enterprise license (kapalı ekosistem), video analytics domain (scope dışı)

## §2 — Mind pillar (2 repo)

### agentmemory (rohitg00, Apache-2.0)
- **Storage:** SQLite (iii-engine StateModule), file-based (harici DB yok)
- **Hibrit retrieval:** BM25 + Vector + Graph (RRF fusion); 51 MCP tool + 12 hook + 104 REST endpoint
- **Tier model:** 4-tier consolidation + decay + auto-forget
- **Decay formula:** `strength * pow(0.9, decayPeriods)` deterministic + cheap
- **Auto-forget:** `forgetAfter` field + contradiction-similarity 0.9 (`auto-forget.ts:9-20`)
- **Cascade supersession:** stale-flagging on graph (`cascade.ts:25-50`)
- **LongMemEval R@5 95.2% iddiası:** Doğrulanması gerek — own benchmark
- **Direkt alınabilir (M6):** TTL/auto-forget pipeline → `packages/mind/forget/`; cascade pattern (bi-temporal fallback); decay formula

### claude-context (zilliztech, MIT)
- **Scope:** Codebase-as-context (kod arama MCP). Bizim "memory" değil, complementary
- **Vector DB:** Milvus/Zilliz Cloud (ZORUNLU external) — bizim offline-first hedefe ters
- **Embedding:** OpenAI/Voyage/Gemini/Ollama pluggable
- **Code chunking:** **tree-sitter AST splitter (9 dil)** + LangChain fallback
- **Incremental sync:** Merkle DAG + SHA-256 file hashes
- **MCP server:** `@zilliz/claude-context-mcp`
- **Direkt alınabilir (M6):** tree-sitter AST splitter → `packages/mind/ingest/codebase/` semantic chunking; Merkle DAG incremental sync pattern

## §3 — Orchestrator (1 repo)

### Archon (coleam00, MIT)
- **Mimari:** Bun + TypeScript monorepo (11 paket). YAML-driven DAG executor — `.archon/workflows/*.yaml`
- **Node types:** `command | prompt | bash | script | loop | approval | cancel`
- **Determinism:** DAG topological layering + `nodeOutputs` map (`$nodeId.output` ref) + resume = re-run skipping completed nodes + event log (8 tablo SQLite)
- **CLI integration:** ClaudeProvider + CodexProvider + PiProvider (~20 LLM)
- **`ProviderCapabilities` flag matrix:** sessionResume/mcp/hooks/skills/agents/toolRestrictions/structuredOutput/envInjection/costControl/effortControl/thinkingControl/fallbackModel/sandbox
- **`MessageChunk` discriminated union:** assistant|system|thinking|result|rate_limit|tool|tool_result|workflow_dispatch + flush flag + toolCallId correlation
- **Worktree isolation per run** — git worktree + path-exclusive lock
- **Bizimle çakışma:** Bizim round-loop Jr-driven adaptive flow Archon'un static-DAG dayatmasından daha esnek
- **Direkt alınabilir (M6 polish):** ProviderCapabilities matrix → cli_agent capability typing; MessageChunk normalization; resume-by-completed-step pattern (resume strategy); git worktree isolation (multi-task paralel için)

## §4 — Audit (1 repo) — **NEGATIVE FINDING**

### hermes-agent (NousResearch, MIT) — **AJAN 9 FALSE-POSITIVE**
- **Audit-god Ajan 9 raporundaki "Issue #487 Cryptographic Audit Trail (SHA-256 hash-chained)" atfı YANLIŞ**
- **Tüm repoda `audit.py`/`trail.py`/`AuditLog`/`prev_hash → event_hash chain` BULUNAMADI**
- Sadece var: `agent/redact.py` regex secret redaction + `agent/lsp/eventlog.py` standart Python logging
- `Grep "#487"` → tek hit `RELEASE_v0.8.0.md:96` ama "#4872" (Honcho holographic prompt) — başka PR
- **Hash chain SOC2 pattern için alternatif kaynak gerek:** AWS QLDB, Hyperledger Fabric, RFC 6962 Merkle CT log, Sigstore Rekor
- **ADR-005 §Sınırlamalar 22 (Hash chain SOC2) içinde hermes referansı YOK** — eklenmesin

## §5 — Reflex M7 (2 repo)

### GenericAgent (lsdefine, MIT)
- **NOT weight update — pure prompt + filesystem**
- L0-L4 memory layers (kodda doğrulanmış: `memory/global_mem.txt` L2, `memory/global_mem_insight.txt` L1, `do_start_long_term_update` L3 SOP distill)
- Agent kendi `file_write` ile `.md`/`.py` skill dosyalarını yazıyor
- **Direkt alınabilir (M7 audit log → SFT):** `_clean_content` (code-block ≥6 satır → preview + count); summary disiplini (her turda `<summary>` zorunlu); 10-turda tool schema reset

### evolver (EvoMap, **GPL-3.0** ⚠️)
- **NOT genetic programming — parametrik prompt seçimi**
- "Prompt generator, not code patcher" (README:163)
- **EvolutionEvent JSONL şeması:** `id`, `parent`, `intent`, `signals[]`, `genes_used[]`, `mutation_id`, `personality_state{rigor,creativity,verbosity,risk_tolerance,obedience ∈ [0,1]}`, `blast_radius{files,lines}`, `outcome{status,score}`
- **PersonalityState drift:** **REDDET** — deterministic loss prensibimize ters; over-engineering
- **Rollback = git revert** (kendi diff store'u yok)
- **GPL-3.0 — kod kopyalama YASAK**; sadece şema ilhamı
- **Direkt alınabilir (M7 SFT dataset):** EvolutionEvent şeması → M5 audit log'a `outcome.score ∈ [0,1]` + `signals[]` + `parent_id` field'ları ekle; Yamaç-only weighted loss filter için

## §6 — Skills/CLAUDE.md (5 repo)

### mattpocock/skills (MIT) — **EN DEĞERLİ (5/5)**
- Bucket organizasyonu (`engineering/`, `productivity/`, `misc/`, `personal/`, `in-progress/`, `deprecated/`)
- 28 SKILL.md + Karpathy disiplini ile %100 felsefi uyum
- **Anti-patterns:** "horizontal slicing" forbidden (TDD vertical-slice)
- **`grill-me` meta-skill** — Yamaç refleksinde "her mesaj sıfırdan değil" + tartışma ritmi eşleşmesi
- **`write-a-skill`** — skill yazmak için skill (meta)

### scientific-agent-skills (K-Dense, MIT) — 3/5
- 135 skill — YAML frontmatter `name` + `description` + `allowed-tools` (zorunlu) + `license` + `metadata.skill-author`
- Cross-skill composition pattern ("uses scientific-schematics skill")
- Progressive disclosure (SKILL.md kısa, `references/` lazy-loaded)

### awesome-codex-skills (ComposioHQ, per-skill MIT) — 3/5
- `$CODEX_HOME/skills/` resolution + `skill-installer` (GitHub'dan tek komutla install)
- Layout convention: `SKILL.md` + `scripts/` (deterministic) + `references/` (lazy) + `assets/`
- Skill dependency: "Depends on the `plan` skill"

### andrej-karpathy-skills (multica-ai, **LICENSE YOK** ⚠️) — 4/5
- Tek dosya `CLAUDE.md` — 4 prensip (Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution)
- **SelfFork CLAUDE.md "Karpathy Disiplini" bölümü ZATEN bu reponun türevi**
- **Eklenmesi gereken:** "These guidelines are working if..." verification listesi (recency reminder)

### TrendRadar (sansan0, **GPL-3.0** ⚠️) — 2/5
- Multi-channel notifier façade (markdown auto-adapts per platform: Feishu 30KB, DingTalk 20KB byte limit)
- 30-second GitHub Actions/Docker deploy
- **Pattern-only — kod kopyalama YASAK**

## §7 — Cross-cutting findings (skills survey)

1. **YAML frontmatter convention** — 5 repodan 4'ünde aynı min sözleşme: `name` + `description` + opsiyonel `allowed-tools`/`license`/`metadata.short-description`
2. **Progressive disclosure standardı** — SKILL.md kısa, uzun içerik `references/`'a (lazy loading = context koruması)
3. **Multi-agent decomposition** — scout-decompose → wave-agents (isolated git worktree) → quality gates (polywave, Vibe-Skills, bernstein patterns)
4. **Yeni MANDATE adayı:** "Tek seferlik prompt skill'e dönüşmez; 3+ tekrar görüldüyse skill'e promote edilir" (write-a-skill türevi)

## §8 — ADR-006 Skill Packs (yeni ADR adayı, M6+)

**Karar:** SelfFork `.selffork/skills/<bucket>/<skill>/SKILL.md` yapısı, YAML frontmatter standardı (`name`/`description`/`allowed-tools`), claude-code + gemini-cli + opencode + codex + mmx üçünün de aynı registry'den okuması.

**Gerekçe:** Prosedürel refleksleri (Yamaç'ın "şöyle yap" paterni) skill'e promote ederek hem reflex training corpus'unu zenginleştir, hem 5 CLI'da paylaşılabilir kıl.

**Referanslar (license uyumlu):** mattpocock/skills + scientific-agent-skills + awesome-codex-skills + financial-services skill format. GPL-3.0 TrendRadar + evolver KOD KOPYALAMA YASAK.

**M6 iter** — M5 close-out sonrası.

---

**Sources:**
- `examples_crucial/{UI-TARS-desktop,cua,CloakBrowser,financial-services,video-search-and-summarization,agentmemory,claude-context,Archon,hermes-agent,GenericAgent,evolver,TrendRadar,scientific-agent-skills,skills,andrej-karpathy-skills,awesome-codex-skills}/`
- 10 explorer-god ajan raporları (2026-05-15)
- 9 audit-god ajan raporları M5 close-out wave (2026-05-15)
- 16 ARGE ajanı raporları M5 başlangıç (2026-05-10)
- `docs/decisions/ADR-005_M5_Body.md` ACCEPTED 2026-05-10
- `docs/M5_SESSION_HANDOFF.md` (next session pickup)
