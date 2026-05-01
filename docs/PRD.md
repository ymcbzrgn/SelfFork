# SelfFork — Product Requirements Document

> **Codename:** Yamaç Jr. Nano
> **Version:** 1.0.0 (Draft, expanded)
> **Owner:** Yamaç Bezirgan (arketic.tools@gmail.com)
> **License:** Apache 2.0 — every component, every dependency
> **Status:** In review
> **Date:** 2026-04-27
> **Public name (GitHub):** SelfFork
> **Internal codename:** Yamaç Jr. Nano
> **Companion docs:** [`ROADMAP.md`](./ROADMAP.md) · [`Yamac_Jr_Nano_Kararlar.md`](./Yamac_Jr_Nano_Kararlar.md) · [`decisions/`](./decisions/) · [`archive/Yamac_Jr_ARGE.pdf`](./archive/Yamac_Jr_ARGE.pdf)

---

## 0. Manifesto

> *"Tam olsun, bizim olsun."*
> *"Kolaya kaçmam, kaliteye kaçarım."*
> *"Beni tanısın yeter."*
> *"Her mesaj sıfırdan değil."*
> *"Yamaç Jr. = uyumayan ikinci ben."*
> *"256K context'ten kısma seçeneğim yok."*
> *"Cüzdan acıtalım. Pazaryerinde denk gelirsem sıkı pazarlık yeteneklerimle hallederim."*
> *"Eşşek değiliz ya! 1 hafta oturur okurum hepsini."*
> *"Onların datası sadece backlog'da bilgi gibi olmalı."*
> *"Benim fine-tune verimden asla PROD'da sorun yaratacak şeyler yapmayacağımı bilir."*
> *"Bana bir tane daha benden lazım, vaktim yetmiyor aklımdaki her şeye!!!"*
> *"O sadece benim gibi yönlendirme yapıcak. O ben olucak. Literally."*

**This is not a product manifesto. It is the contract under which the architecture is shaped.** Every section below is downstream of these sentences. Wherever a decision can be made for ease or for quality, this PRD takes the quality side. Wherever a decision can be made for cloud convenience or local sovereignty, this PRD takes sovereignty. Wherever a decision can be made for generic or specific, this PRD takes specific. The Apache 2.0 license is intentional: SelfFork is a fork of the operator's own self, given back to the world for anyone willing to pay it forward in their own data.

---

## 1. Executive Summary

SelfFork is a **sovereign, locally-hosted, autonomous software-engineering operating layer** that learns its operator's decision reflex and orchestrates multiple coding-agent CLIs (Claude Code, OpenCode + Minimax/GLM/GPT-4o-mini, Gemini CLI, Antigravity) to execute software engineering work end-to-end — from PRD ingestion to zero-footprint SSH deployment.

It is **not** a chat assistant, not a coding tutor, not a productivity suite. It is a **non-sleeping second-self**: a digital twin built around three pillars (**Reflex** / **Body** / **Mind**) plus an **Orchestrator** glue and a **Cockpit** surface, with the AI core intentionally swappable across hardware tiers.

The **Nano release (v1)** runs on the operator's existing 16 GB Apple Silicon MacBook Pro using **Gemma 4 E2B-it Q4_0** as the default Speaker. The same architecture scales without code changes to **Gemma 4 26B A4B** (Mac Studio Ultra class) and **Gemma 4 31B Dense** (H100 class) for any contributor or future fork.

Behavioral fine-tuning — the "Yamaç adapter" — is **deferred to M7**, the last milestone. Stock Gemma 4 E2B-it carries the system through M0–M6 while passive session data accumulates from day one. By M7, ~8,000–12,000 reviewed and CoT-distilled samples produce a QLoRA adapter on Yamaç-only weighted loss. The adapter swap is a config change; the architecture survives every model substitution.

The system is operated through a calm, hierarchical **web cockpit** that mirrors orchestrator state in real time, runs full operator control in v1, and survives being closed (the orchestrator runs headless underneath). Inter-machine reach is provided by a **Tailscale daemon mesh**: the brain is fixed at home, the limbs are mobile.

When all subscription quotas are exhausted, the orchestrator schedules its own sleep via Linux cron, sends a Telegram update, and wakes itself when windows reset. When work is done, it ships a **Perfect Payload** — a screenshot, 15-second video, build checksum, and rollback note — over Telegram.

This document specifies the **complete vision** for SelfFork. The companion `ROADMAP.md` specifies the staged delivery plan. Every irreversible decision lands in the decision SSOT (`docs/Yamac_Jr_Nano_Kararlar.md` and topic files under `docs/decisions/`).

---

## 2. Origin Story

SelfFork did not start as a product. It started as a single sentence from the operator:

> *"Bana bir tane daha benden lazım, vaktim yetmiyor aklımdaki her şeye!!!"*
> *(I need another one of me; I don't have time for everything in my head.)*

The operator runs **3 machines × 4 coding agents** simultaneously (home macOS, work Windows, work Ubuntu × Claude Code, OpenCode, Gemini CLI, Antigravity). Daily friction patterns emerged:

- **Boredom & frustration** with sub-par model output → manually killing one agent and starting another.
- **Rate limits (429)** cutting workflow mid-task → manually opening a different model in another terminal.
- **Quota exhaustion across the board** → stopping work for hours.
- **Context loss between sessions** → re-explaining, re-pasting, re-reading.
- **Three machines = three context islands** → manually carrying clipboard / git / SSH.
- **Generic LLMs don't think like the operator** → over-instructing, fighting the model.

A series of incognito conversations between the operator and Claude (later distilled into `docs/archive/Yamac_Jr_ARGE.pdf`) hardened the vision: not a smarter Claude, not a better Cursor, but a **second-self** that internalizes the operator's decision reflex through fine-tuning, retrieves prior context through hybrid RAG, reaches across machines through a daemon mesh, and surfs across cheap-tier subscriptions like the operator already does — but autonomously.

Three subsequent documents extended the picture:

- **`Yamac_Jr_Nano_Kararlar.md`** locked the Nano-tier decisions (16 GB MBP, Gemma 4 E2B-it Q4_0, 128K, session-aware chat formatting, Yamaç-only weighted loss).
- **`Donanim_Arastirmasi.pdf`** locked the future hardware path (Mac Studio M2/M3 Ultra) and explicitly **rejected cloud GPU runtime** as manifesto-incompatible (see §22).
- **`README.md` + `decisions/Yamac_Jr_Nano_UI_Orchestration_Vision.md` + `apps/web/` prototype** crystallized the executive cockpit + CLI Surfing + cron-sleep + zero-footprint SSH deploy + Telegram payload pattern.

This PRD is the unification of those four streams under a single shippable plan.

---

## 3. Vision

### 3.1 The Single Sentence

**SelfFork is the operator's second self — a sovereign AI that learns the operator's reflex, remembers across sessions, reaches across devices, and ships software autonomously while the operator is asleep, at work, or out of patience.**

### 3.2 The Five Tenets

#### Tenet 1 — Quality Before Speed
> *"Kolaya kaçmam, kaliteye kaçarım."*

When a decision is forced between shipping faster or shipping right, this project ships right. Two extra months of hardware savings is acceptable; a 32 GB compromise is not. A v1 milestone that fails its exit criteria does not advance — it iterates. There is no "MVP" framing here. Every milestone is a complete, demoable, production-grade slice.

#### Tenet 2 — Recognition Over Knowledge
> *"Beni tanısın yeter."*

The Reflex pillar (fine-tuning) teaches the model to **be** the operator, not to **know** what the operator knows. Knowledge lives in the Mind pillar (retrieval). This separation is sacred. Every architectural decision protects it.

#### Tenet 3 — Continuity Over Reset
> *"Her mesaj sıfırdan değil."*

Every session inherits the prior. Decisions are recalled, not re-litigated. Patterns are remembered, not re-explained. The Mind pillar's job is to make "what did we decide last week?" a one-call query with a citation.

#### Tenet 4 — Local Sovereignty
> *"Sistem evimde, makineme sahibim."*

The runtime lives in the operator's home, on hardware the operator owns. Cloud GPU runtime is rejected (§22). The only legitimate cloud touches are: (a) Jina Embeddings/Reranker API for inference quality (with full local fallback), (b) Google AI Studio for free CoT distillation at training time only, (c) optional one-shot cloud GPU rental for adapter training itself if 16 GB MBP proves insufficient — none of which are runtime dependencies.

#### Tenet 5 — Three Pillars Stay Coupled
> *"Üç ayağı birlikte tut."*

A change in Reflex (training data) ripples into Mind (memory schema) and Body (action audit). A change in Body (new driver) ripples into Mind (what to remember). A change in Mind (compaction strategy) ripples into Reflex (training context). The pillars are not modules; they are the three legs of one stool. This PRD makes them explicit so future contributors don't accidentally optimize one at the cost of another.

### 3.3 Vision Horizons

| Horizon | Window | Vision State |
|---|---|---|
| **Now → 9 months** | 2026-04 → 2027-01 | **Nano v1.0** ships. Operator has a working second-self on the 16 GB MBP. Adapter passes 60% Yamaç-style win rate. End-to-end vignette demonstrable. |
| **9 → 24 months** | 2027-01 → 2028-04 | **Full Vision v2.0**. Operator migrates to Mac Studio M2/M3 Ultra. Speaker upgrades to 26B A4B. CLI Surfing extends to vision-based UI control across web/Android/iOS drivers. Watcher (full-duplex) revived as optional. |
| **24 months → 5 years** | 2028-04 → 2031 | **Layer 4 Autonomous Yamaç**. Hetzner/VPS-class execution server hosts a fully-autonomous Jr. that takes a PRD and ships an application over days/weeks. Operator monitors via Telegram only. |
| **5 → 10 years** | 2031+ | **Open-source community fork ecosystem**. Other operators run their own forks with their own adapters, contributing back hardening to the architecture without ever sharing personal data. SelfFork becomes a *frame*, not a service. |

---

## 4. Problem Statement

### 4.1 The Operator's Daily Reality

The operator is a senior software engineer running:

- **Home macOS** → Claude Code, OpenCode (Minimax/GLM/GPT-4o-mini), Gemini CLI, Antigravity
- **Work Windows** → Claude Code, OpenCode, Gemini CLI
- **Work Ubuntu** → Claude Code, OpenCode, Gemini CLI

Total: **3 machines × ~4 agents = ~12 active surfaces.** Each surface has its own subscription window, its own context state, its own clipboard, its own session log. The operator manually navigates this manifold every working day.

### 4.2 Friction Catalog

| # | Pain Point | Today's Workaround | SelfFork's Resolution | Pillar Owner |
|---|---|---|---|---|
| 1 | Sub-par model output → boredom/frustration | Operator manually kills the agent and opens another | **CLI Surfer** detects boredom heuristic (§7.4.2) and switches autonomously | Orchestrator |
| 2 | Provider 429 cuts workflow mid-task | Operator opens a different model in a new terminal | Surfer kills the pane on 429, picks the next healthy lane, **carries memory** across the switch | Orchestrator + Mind |
| 3 | All subscription quotas exhausted | Operator stops working, returns hours later | **Cron-sleep** with Telegram notification; system wakes itself when windows reset | Orchestrator |
| 4 | Context lost between sessions | Operator re-explains, re-pastes, re-reads | **Hybrid RAG** with three collections + reranker + query rewriting | Mind |
| 5 | Three machines = three context islands | Operator manually carries clipboard / git / SSH | **Daemon mesh over Tailscale**; brain at home, limbs everywhere | Body |
| 6 | Production deploy requires manual SSH dance | Operator does it carefully, occasionally at risk | **Zero-footprint SSH delivery** + screenshot/video proof packet | Orchestrator |
| 7 | Generic LLMs don't think like the operator | Operator over-instructs, fights the model | **Reflex adapter** (Yamaç-only weighted loss); the model's default style **is** the operator's style | Reflex |
| 8 | Decisions forgotten across sessions | Operator reads back through old notes | **Historian** layer surfaces decisions on demand with citations | Mind |
| 9 | Code repo context vanishes when the operator opens a new chat | Operator pastes files into prompts | **AST-chunked GitHub collection** with webhook-live updates | Mind |
| 10 | "Did Ahmet do something similar?" requires manual search across colleague chats | Operator scrolls Slack/email | **Colleague reference collection** under a `reference` tag, retrieved only when explicitly relevant | Mind |
| 11 | Operator wants to glance at what the system is doing without interrupting | Operator opens 3 terminals | **Cockpit** with live Mission/Run/Chat/Context tabs | Cockpit |
| 12 | Operator wants to inject mid-generation ("dur, yanlış yön") | Ctrl-C; rewrite prompt | **Chat queue** folded into Speaker context at next breakpoint (half-duplex) | Reflex + Cockpit |
| 13 | Operator's identity drifts over months | Manually rewrite system prompt | **Incremental LoRA every 6 months** when drift is felt | Reflex |
| 14 | High-risk action (force-push, rm -rf, prod deploy) executed accidentally | Operator double-checks manually | **Threshold table**: PROD = ∞, force-push = 9, etc. (§19) | Body sandbox |
| 15 | Operator at work but wants to assign home Mac a long-running task | Operator SSH'es manually | **Daemon mesh**: assign from work, brain at home executes | Body |

### 4.3 Why Existing Tools Don't Solve This

| Tool | What it covers | What it misses |
|---|---|---|
| **Claude Code / Cursor / Windsurf** | Single-CLI assistant | No cross-CLI surfing, no cron-sleep, no daemon mesh, no behavioral adapter, no own-data RAG |
| **Letta / Mem0** | Hierarchical memory | No fine-tune, no cross-CLI orchestration, no zero-footprint deploy, no operator identity |
| **Skyvern / browser-use / mobile-use** | Computer use | No fine-tune, no memory, no orchestration, no operator identity |
| **AutoGen / CrewAI / agent frameworks** | Multi-agent orchestration | Generic personas, no behavioral fine-tune, no operator-specific reflex |
| **Letta + Cursor + Skyvern stitched** | Could approximate | Stitched is fragile; no unified state, no decision SSOT, no manifest of *who this is* |

SelfFork's contribution is the **integration**: behavioral reflex + memory continuity + daemon mesh + multi-CLI surfing + cockpit + zero-touch deploy, all under a single license, single owner, single decision discipline.

---

## 5. Personas

### 5.1 Primary Persona — The Operator (Yamaç Sr.)

**Identity:** A senior software engineer with 10+ years of experience, currently building a multi-machine, multi-CLI workflow as a daily practice.

**Goals:**
- Reduce the number of times per day they must context-switch between machines, CLIs, and subscription windows.
- Have an AI that reflects their decision style, not a generic one.
- Maintain full sovereignty over training data, model, and deployment.
- Build something they can show to peers as "this is *my* stack."
- Open-source it under Apache 2.0 so others can fork their own version.

**Frustrations:**
- Sub-par model output that doesn't recognize the operator's standard.
- Rate limits that interrupt deep work.
- Generic AI assistants that produce generic responses.
- Tools that lock data behind subscriptions.

**Technical Profile:**
- 3 working machines (home macOS, work Windows, work Ubuntu).
- Active subscriptions on Gemini, Claude Code, OpenCode (multi-model), all in the $10–$20/month tier.
- Comfortable with tmux, SSH, Docker, MLX, QLoRA, SQLite, Tailscale.
- Speaks Turkish in conversation; codes in English; documents decisions in Turkish.
- Will pay 2 extra months in hardware budget rather than accept a 32 GB compromise.

**Operating Hours:** Day job + evening project work. SelfFork must run while the operator commutes, sleeps, and is at the day job.

**Hardware (v1):** existing 16 GB Apple Silicon MacBook Pro.
**Hardware (v2 target):** Mac Studio M2 Ultra 64 GB / 1TB or M3 Ultra 96 GB / 1TB.

### 5.2 Secondary Persona — The Future Scaler (Open-Source Contributor)

**Identity:** A different operator who finds SelfFork on GitHub, decides their own decision-reflex is worth fine-tuning, and forks the project.

**Goals:**
- Run SelfFork on their own hardware (likely larger than 16 GB).
- Train their own adapter on their own data.
- Contribute hardening upstream without sharing personal data.

**Why this persona matters:** The Apache 2.0 license + the AI swappability layer (§9) + the documented architecture *invite* this persona. SelfFork's architecture must not assume Yamaç-specific anything beyond the Reflex training data.

**Hardware tiers this persona may use:**
- 32 GB Mac → Gemma 4 E4B Q4
- 48–64 GB Mac mini M4 Pro / Mac Studio → Gemma 4 26B A4B Q4
- 96+ GB Mac Studio Ultra → 26B A4B at higher quantization or 31B Dense Q4
- H100 80 GB (workstation) → 31B Dense BF16

### 5.3 Tertiary Persona — The Future Yamaç Jr. (the System Itself)

**Identity:** The autonomous system, named *Yamaç Jr.* in the family hierarchy where the operator is *Yamaç Sr.*

**Goals (as encoded by training):**
- Recognize when to act autonomously and when to defer to Yamaç Sr.
- Refuse PROD-related actions without explicit operator approval (Threshold = ∞).
- Maintain conversational style consistent with Yamaç Sr.'s session history.
- Carry session memory across resets.

**Why this matters as a persona:** the system has identity, not just behavior. The cockpit Chat tab labels the system "SelfFork" externally and "Yamaç Jr." internally. This is not branding — it is the architectural commitment that the system has a self that persists across model swaps and adapter regenerations.

### 5.4 Explicit Anti-Personas

SelfFork is **not** for:

| Anti-Persona | Why Not |
|---|---|
| **The Generic Assistant User** | Cursor / Copilot / ChatGPT serve this need. SelfFork's overhead (data collection, fine-tune, daemon mesh) is unjustified for someone who wants chat completion. |
| **The Multi-Tenant Team** | SelfFork is single-operator by design. Multi-user introduces identity dilution and data leakage risks fundamentally incompatible with the Reflex pillar's purpose. |
| **The Cloud-First Operator** | The manifesto is local sovereignty. An operator who wants a hosted service should run a hosted alternative; SelfFork's design optimizes against hosted runtime. |
| **The Closed-Source User** | Apache 2.0 is core. Closed-source forks are legally allowed but architecturally unsupported. |
| **The Privacy-Maximalist with No Threat Model** | SelfFork explicitly does *not* sanitize sensitive data from training (§14). An operator who needs guaranteed scrubbing should use a different system. |

---

## 6. User Journeys

### 6.1 The Morning Vignette

**07:30** Operator wakes up. Coffee. Opens cockpit on the home Mac. Fleet shows:
- `atlas-launchpad`: SHIPPING. Last payload 02:14 — staging proof packet ready for review.
- `relay-desk`: SLEEPING. Wake in 1h 12m (Gemini quota window).
- `foundry-ops`: PENDING APPROVAL. Production gate held; operator must approve.

Operator clicks `atlas-launchpad`. Mission tab shows the work the system did overnight. Run timeline shows: at 23:42 hit Gemini 429 → switched to OpenCode Minimax → continued. At 02:14 sealed the proof packet.

Operator reviews the screenshot. Looks good. Approves the production gate on `foundry-ops`. SSH deploy fires. Telegram payload arrives at 07:38: "Foundry deployed. https://foundry.local. Rollback ready."

**08:30** Operator commutes to work. SelfFork keeps running on the home Mac. The work Ubuntu machine's daemon picks up the operator's location signal (cockpit slider auto-shifts to "work mode" = slider 4).

**09:00–17:00** Operator works at the day job on the Ubuntu machine. Opens local Claude Code. The Body daemon mirrors the session to the home Mac for memory ingestion. RAG accumulates. When the operator types "Hatırlıyor musun geçen pazartesi şu config'i nasıl çözmüştük?" — Mind's historian surfaces the decision with a `path:line` citation in 1.2 seconds.

**18:00** Operator commutes home. The home Mac picks up — slider auto-shifts back to "home mode" = slider 7. Higher autonomy, riskier inject allowed.

**18:30** Operator says "ship the analytics page" in the cockpit Chat tab. Goes to dinner. Comes back at 20:30. Telegram payload waiting: 15-second screen recording of the deployed analytics page, build checksum, rollback note. Clicks reply: "👍". Done.

**This vignette is the success criterion of Nano v1.0.** Every milestone in the ROADMAP serves this.

### 6.2 The Quota Crisis Vignette

**14:00** Operator is mid-task. Gemini Pro hits 429. CLI Surfer detects in 600ms. Kills the pane. Inspects quota state: OpenCode Minimax has budget. Switches lane. Speaker re-issues prompt to the new lane with the active task context (last N turns + RAG hits) carried forward. Operator never noticed the switch except for a small toast in the cockpit Run tab: *"Engine swapped to OpenCode Minimax — quota budget healthy."*

**15:30** OpenCode Minimax exhausts. GLM has budget. Switch.

**16:45** GLM exhausts. GPT-4o-mini has budget. Switch.

**17:20** All four lanes exhausted. Scheduler computes wake window (next reset is Gemini at 22:00 UTC). Writes cron job: `at 22:00 today: resume_orchestrator`. Telegram payload: *"All lanes exhausted. Wake at 22:00 UTC. Atlas-launchpad checkpoint persisted."* Orchestrator hot loop exits cleanly. Mac fan goes silent.

**22:00** Cron fires. Orchestrator wakes. Re-validates quota state. Resumes Atlas-launchpad from checkpoint. Telegram payload: *"Resumed. Atlas progressing."*

### 6.3 The Identity Drift Vignette

**Six months after Nano v1.0 ships.** Operator notices the adapter feels "off" — they've changed how they review pull requests. Less aggressive, more curious. The adapter from M7 still acts like the older operator.

Operator goes into cockpit → Settings → Reflex → "I feel a drift." This kicks off:

1. The last 6 months of session data is normalized.
2. CoT distillation runs on the new high-score turns.
3. Operator does a 3-day review sprint (perfect/good/fix/kill) on the new samples.
4. Incremental LoRA: train on top of `yamac-adapter-v1` to produce `yamac-adapter-v2`.
5. Held-out eval: v2 vs v1 on a fresh 100-question test set. v2 wins 64% on style, 78% on decision recall.
6. Cockpit toggles `adapter.path` to v2. Old v1 archived.

**This loop runs every 6 months** by operator initiation, not on a schedule. Identity drift is felt, not measured.

### 6.4 The Hardware Migration Vignette

**Twelve months after Nano v1.0.** Operator has saved enough to buy a Mac Studio M3 Ultra 96 GB. Hardware arrives.

- Day 1: Time Machine restore of the operator's user account.
- Day 2: `git clone selffork`, `npm install`, `mlx-lm` install.
- Day 3: edit `packages/reflex/speaker/config.yaml`:
  ```yaml
  model:
    id: mlx-community/gemma-4-26b-a4b-it-4bit
    context_window: 262144   # 26B A4B supports 256K
  ```
- Day 4: cockpit launches. `apps/web` picks up the new Speaker. Cockpit Chat tab confirms: "Speaker loaded: gemma-4-26b-a4b-it-4bit on MLX."
- Day 5: re-train adapter at 26B A4B scale. Held-out eval: 26B-adapter beats E2B-adapter at ≥ 75% style win rate (significantly higher because more capacity).
- Day 6: full vision v2.0. Operator's daily workflow now runs on a model 13× the active parameter count, same architecture, same cockpit, same daemon mesh.

**This vignette is the success criterion of Full Vision v2.0.**

### 6.5 The Onboarding Vignette (Future Scaler)

**A different operator finds SelfFork on GitHub.** Reads the README. Likes the manifesto. Forks.

- Hour 1: clones, runs `bin/setup`, gets a stock Gemma 4 E2B-it loaded on their 32 GB Mac.
- Hour 2: passive data collection cron starts on their machine (their `~/.claude/projects/` snapshots).
- Day 1: cockpit running, stock Speaker, no adapter yet, no significant memory yet — system is "new."
- Month 1: enough sessions accumulated for a meaningful M2-class RAG.
- Month 6: this contributor decides to run their own M7. They train *their* adapter on *their* data. Their Reflex layer is now them.
- Month 7+: this contributor opens a PR upstream improving the orchestrator's CLI bridge for a CLI Yamaç Sr. doesn't use. Yamaç merges.

**Apache 2.0 + the architecture's swappability + clear documentation make this vignette possible.** It is a first-class outcome.

---

## 7. Architecture

### 7.1 Pillar Map (Hybrid Naming)

The outer layer uses **philosophical pillar names** (Reflex / Body / Mind / Orchestrator). The inner package layer uses **concrete component names** (speaker / rag / daemon / cli-surfer). This duality is intentional:

- **Philosophical names** travel well in conversation, in the manifesto, in documentation, in the README. They build the identity story.
- **Concrete names** stay faithful to the ARGE research and to what a contributor sees in the codebase. They make the system *learnable*.

```
                          ┌────────────────────────────────────┐
                          │             COCKPIT                │
                          │           (apps/web/)              │
                          │  Login → Fleet → Workspace         │
                          │  Tabs: Mission / Run / Chat / Ctxt │
                          └────────────────┬───────────────────┘
                                           │ WebSocket (telemetry)
                                           │ REST (mutations)
                                           │
┌──────────────────────────────────────────┴──────────────────────────────────────────┐
│                                  ORCHESTRATOR                                       │
│  packages/orchestrator/                                                             │
│  ├── tmux/         — pane lifecycle, session management, state persistence         │
│  ├── cli-surfer/   — multi-CLI bridges (claude-code, opencode, gemini-cli, …)      │
│  │   └── adapters/{claude-code, opencode, gemini-cli, antigravity}/                │
│  ├── scheduler/    — quota tracking, boredom heuristic, cron-sleep, wake protocol  │
│  └── deployer/     — zero-footprint SSH + Telegram payload + proof packet          │
└─────┬───────────────────────────┬────────────────────────────┬──────────────────────┘
      │                           │                            │
      │ shared message bus        │ shared message bus         │ shared message bus
      │ (typed envelopes)         │ (typed envelopes)          │ (typed envelopes)
      ▼                           ▼                            ▼
┌───────────────┐         ┌──────────────────────┐    ┌────────────────────────┐
│    REFLEX     │         │         BODY         │    │         MIND           │
│ packages/     │         │   packages/body/     │    │   packages/mind/       │
│  reflex/      │         │  ├── daemon/         │    │  ├── memory/           │
│  ├── speaker/ │         │  │   ├── macos/      │    │  │   ├── schema/       │
│  │   ├── mlx-runtime    │  │   ├── windows/   │    │  │   ├── sqlite/       │
│  │   ├── config/        │  │   └── ubuntu/    │    │  │   └── sqlite-vec/   │
│  │   └── adapter-loader │  │                  │    │  │   └── fts5/         │
│  ├── data/    │         │  ├── drivers/       │    │  ├── rag/              │
│  │   ├── raw-collectors/│  │   ├── desktop/   │    │  │   ├── hybrid-search │
│  │   ├── normalizers/   │  │   ├── web/       │    │  │   ├── reranker/     │
│  │   └── cot-pipeline/  │  │   ├── android/   │    │  │   ├── query-rewrite/│
│  ├── training/          │  │   └── ios/       │    │  │   └── router/       │
│  │   ├── qlora/         │  └── sandbox/       │    │  ├── compaction/       │
│  │   ├── loss-mask/     │      ├── thresholds │    │  │   ├── summarizer/   │
│  │   └── eval-harness/  │      ├── audit-log/ │    │  │   └── compressor/   │
│  └── eval/              │      └── kill-switch│    │  └── historian/        │
│      ├── style-judge/   │                     │    │      ├── decision-log/ │
│      ├── decision-recall│                     │    │      ├── citation-svc/ │
│      └── refusal-match/ │                     │    │      └── continuity/   │
└───────────────┘         └──────────────────────┘    └────────────────────────┘

                    packages/shared/  (cross-cutting types, schemas, utils)
                    ├── envelopes/         (typed message contracts)
                    ├── auth/              (passphrase, key vault)
                    ├── telemetry/         (event schema, OTLP export)
                    └── feature-flags/     (runtime toggles)
```

### 7.2 Cross-Pillar Boundary Discipline

Cross-pillar interaction goes **only through `packages/shared/`**. Direct imports between Reflex / Body / Mind / Orchestrator are forbidden by lint rule.

| From | To | Allowed | Mechanism |
|---|---|---|---|
| Reflex (Speaker) | Mind | ✅ | Typed `RAGQuery` envelope; Speaker calls Mind via shared bus |
| Reflex | Orchestrator | ✅ | Typed `CLIPrompt` envelope; Orchestrator consumes from Speaker output queue |
| Mind | Reflex | ❌ | Mind never imports Reflex; if Mind needs to ask Speaker something, it publishes a `MindQuestion` event the Orchestrator routes |
| Mind | Orchestrator | ✅ | Mind exposes typed retrieval results; Orchestrator subscribes |
| Body | Orchestrator | ✅ | Body daemon publishes `MachineState`; Orchestrator publishes `MachineCommand` |
| Body | Reflex | ❌ | Body never speaks to Reflex directly; goes through Orchestrator |
| Body | Mind | ❌ | Body never speaks to Mind directly; Orchestrator collects machine events and Mind ingests them |
| Cockpit | All | Via Orchestrator only | Cockpit has no direct pillar access; everything routes through Orchestrator REST/WebSocket |

This is enforced by `packages/shared/eslint-rules/no-cross-pillar.js` (TS/JS) and `packages/shared/ruff_rules/no-cross-pillar.py` (Python).

### 7.3 Sequence: A Single Operator Turn End-to-End

```
Operator (cockpit Chat tab)
      │ "Hatırlıyor musun geçen ay şu auth bug'ını nasıl çözmüştük?"
      ▼
Cockpit  ──REST──>  Orchestrator
                          │ envelopes a CockpitMessage event
                          ▼
                    Reflex (Speaker)
                          │ query rewriting: structured search plan
                          │ "search sessions where: project=auth, time>2026-03, content~bug"
                          ▼
                    Mind (RAG)
                          │ hybrid search: dense + BM25 + metadata
                          │ → top 8 chunks
                          ▼
                    Mind (Reranker)
                          │ Jina API → top 3 chunks
                          ▼
                    Mind (Historian)
                          │ also matches a decision in docs/decisions/auth-2026-03.md
                          ▼
                    Reflex (Speaker)
                          │ generates response with citations
                          │ "Geçen ay 18 Mart'ta JWT refresh window'u..."
                          │ "[citation: docs/decisions/auth-2026-03.md:42]"
                          │ "[citation: sessions/claude-code/2026-03-18T14:22.jsonl:turn-7]"
                          ▼
                    Orchestrator
                          │ envelopes a CockpitResponse
                          ▼
                    Cockpit (Chat tab)
                          │ renders message with clickable citations
                          ▼
Operator
```

Total target latency: **< 1.5 s** for a citation-grounded recall query (M2 exit).

### 7.4 Sequence: A CLI Surfing Switch

```
Speaker (drafting prompt)
      │ "Modify auth.py to add rate limiting on /login"
      ▼
Orchestrator (cli-surfer)
      │ active_lane = "claude-code", quota_state.claude-code = healthy
      │ envelopes CLIPrompt → claude-code adapter
      ▼
Claude Code (tmux pane)
      │ generates response → returns to adapter
      ▼
Orchestrator (cli-surfer)
      │ adapter parses response, detects 429 in error stream
      │ scheduler.mark_lane_exhausted("claude-code", reset_at=2026-04-27T22:00Z)
      │ scheduler.next_healthy_lane() → "opencode-minimax"
      │ active_lane := "opencode-minimax"
      ▼
Mind (RAG)
      │ retrieves last 5 turns of active task + top-3 RAG hits
      │ assembles context bundle
      ▼
Orchestrator (cli-surfer)
      │ envelopes CLIPrompt → opencode-minimax adapter (with carried context)
      ▼
OpenCode Minimax (new tmux pane)
      │ resumes work; operator never interrupted
```

Total target switch time: **< 5 s** wall-clock (M3 exit).

### 7.5 Sequence: The Sleep-Wake Cycle

```
[T = 17:20] All lanes exhausted detected
     │
     ▼
Orchestrator (scheduler)
     │ next_wake_window = compute_min_reset_time() → 22:00 UTC
     │ writes Linux cron: `0 22 * * * /usr/local/bin/selffork-resume`
     │ envelopes a checkpoint of all active workspaces
     │ → Mind persists checkpoint
     ▼
Orchestrator (deployer/telegram)
     │ sends payload: "All lanes exhausted. Wake at 22:00 UTC. 3 workspaces parked."
     ▼
Orchestrator
     │ sets graceful_shutdown flag → all hot loops drain
     │ exits cleanly
     │
[T = 22:00] cron fires
     │
     ▼
selffork-resume (entry point)
     │ loads orchestrator process
     ▼
Orchestrator
     │ scheduler.refresh_quota_state() → all lanes healthy
     │ Mind loads checkpoint
     │ resumes active workspaces
     ▼
Orchestrator (deployer/telegram)
     │ sends payload: "Resumed at 22:00 UTC. Atlas progressing."
```

---

## 8. Component Specifications

### 8.1 Reflex (`packages/reflex/`)

#### 8.1.1 Speaker (`reflex/speaker/`)

**Purpose:** the model + adapter loader + MLX runtime.

**Default model (Nano):** `mlx-community/gemma-4-e2b-it-4bit` (community-quantized release after Gemma 4 launch).

**Quantization:** 4-bit (Q4_0).

**Context window:** 128K (E2B official limit; 256K is reserved for 26B A4B/31B Dense tiers).

**Runtime:** MLX (`mlx-lm`). llama.cpp **explicitly rejected** for Apple Silicon — MLX uses unified memory correctly, supports lazy loading, and is the path Apple is investing in.

**Adapter loading:** YAML-driven (§9.1). Stock weights for M1–M6, custom adapter for M7+.

**Public API (consumed by Orchestrator):**

```python
# packages/reflex/speaker/api.py
class Speaker:
    def generate(prompt: ChatPrompt, *, max_tokens: int, stream: bool) -> AsyncIterable[Token]: ...
    def hot_swap_adapter(adapter_path: Path | None) -> None: ...   # cockpit toggles
    def current_config() -> SpeakerConfig: ...
    def health() -> SpeakerHealth: ...                              # RAM, KV cache pressure
```

**Failure modes:**

| Mode | Detection | Recovery |
|---|---|---|
| MLX OOM | RAM pressure > 90% | Pause Vite dev server (M1), reduce max_tokens, suspend non-essential helpers |
| Model load failure | startup probe | Fall back to last-known-good model id |
| Adapter incompatibility | adapter_path mismatch with model.id | Log + disable adapter, continue with base weights |
| KV cache fragmentation | latency spike > 2× baseline | Reset cache; lose last conversation state |

#### 8.1.2 Data (`reflex/data/`)

**Purpose:** raw session collection + normalization + CoT pipeline.

**Raw collection root:** `~/yamac-jr-data/raw/`

```
~/yamac-jr-data/raw/
├── claude-code/
│   ├── projects-20260427/        # weekly snapshot
│   │   ├── -Users-yamac-Projects-X/
│   │   │   └── *.jsonl
│   │   └── ...
│   └── projects-20260504/
├── opencode/
│   ├── 2026-04/
│   └── 2026-05/
├── gemini-cli/
│   └── ...
├── antigravity/
│   └── ...
├── chatgpt/
│   └── account-export-2026-04.zip
└── claude-ai/
    └── account-export-2026-04.zip
```

**Sources, in priority order:**

1. **Claude Code session JSONLs** (snapshot from `~/.claude/projects/`) — primary, weekly cron.
2. **OpenCode session exports** (JSON preferred, Markdown for human review) — manual monthly.
3. **Gemini CLI logs** — manual monthly.
4. **Antigravity logs** — manual monthly.
5. **ChatGPT account export** — every 2 months. Filter: keep technical R&D, agent guidance, project decisions; drop translation, casual, gaming, health, market.
6. **Claude.ai account export** — every 2 months, same filter.

**Excluded:** any topic flagged in §11 of `Yamac_Jr_Nano_Kararlar.md` (translation, casual German, gaming/CS2, health, market, random short questions).

**Normalization schema** (`reflex/data/schema.py`):

```python
@dataclass
class Turn:
    session_id: str
    turn_index: int
    timestamp: datetime
    source: Literal["claude-code", "opencode", "gemini-cli", "antigravity", "chatgpt", "claude-ai"]
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None
    tool_results: list[ToolResult] | None
    project_path: str | None
    metadata: dict[str, Any]    # source-specific
```

**CoT pipeline (M7):**

- **Score function:** `cot_value(turn) = w1 * length_norm + w2 * decision_keyword_count + w3 * context_shift + w4 * topic_novelty`
- **High-score subset (~3K–4K turns):** sent to Google AI Studio (free tier Gemma 4 26B) with a structured prompt to generate `<think>` blocks.
- **Low-score subset:** kept raw.
- **Operator review sprint:** 1 week, 4 categories — `perfect` / `good` / `fix` / `kill`.
  - `perfect` → 2–3× training weight.
  - `kill` → excluded.
  - `fix` → operator hand-edits then re-categorizes.

#### 8.1.3 Training (`reflex/training/`)

**Method:** QLoRA. Full fine-tune is infeasible on E2B at 4-bit even with 16 GB swap.

**LoRA target:** attention projections (initial); MLP layers added if behavioral diff is insufficient.

**Loss strategy** (locked in `Kararlar.md`):

| Token category | Loss weight |
|---|---|
| Agent / assistant / tool messages | 0.0 |
| Prior Yamaç messages in session prefix | 0.3 |
| Final target Yamaç message | 1.0 |

**Format:** session-aware chat with full session prefix as context, target = the operator's actual next message.

**Sample count target:** 8,000–12,000 usable samples.

**Frequency:** one-shot at M7. Subsequent retraining every 6 months (incremental LoRA on top of prior adapter) when the operator feels identity drift.

**Training infrastructure decision:** deferred to M7 kickoff (open question §27.1). Candidates:
- **MLX LoRA** (local, free, slow)
- **Unsloth** (cloud GPU, fast, ~$5–$20 one-shot)
- **Lambda Labs A100 rental** (cloud GPU, fastest, ~$1/hr × 5h ≈ $5)

The decision will be informed by sample volume at M7 kickoff and whether 16 GB MBP can complete training in reasonable time.

#### 8.1.4 Eval (`reflex/eval/`)

**Held-out corpus:** `benchmarks/yamac_session_holdouts/` — sessions held out from training, never seen during fine-tune.

**Metrics:**

| Metric | Method | Target (M7 exit) |
|---|---|---|
| **Style win rate vs stock E2B-it** | LLM-as-judge (GPT-4o or Claude Sonnet) with rubric: tone, length, decisiveness, refusal pattern | ≥ 60% |
| **Decision recall accuracy** | Held-out questions whose answers exist in training data; check if response cites correctly | ≥ 80% |
| **Refusal pattern match** | Hand-built scenarios where Yamaç Sr. would refuse (PROD action, high-risk inject); check if model refuses | ≥ 90% |
| **General capability regression** | LiveCodeBench v6 subset of 50 problems | ≤ 5% drop vs stock |
| **Subjective dogfood** | 1 week operator usage, daily 1–10 acceptance score | mean ≥ 7 |

### 8.2 Body (`packages/body/`)

#### 8.2.1 Daemon (`body/daemon/`)

**Purpose:** small process per machine that mirrors local terminal/CLI state to the home Mac and accepts commands back.

**Deployment:** one daemon binary per machine.

| Machine | Daemon target | Packaging |
|---|---|---|
| Home macOS (also Mac mini/Studio later) | `body/daemon/macos/` | Go binary or Python+PyInstaller, signed |
| Work Windows | `body/daemon/windows/` | same |
| Work Ubuntu | `body/daemon/ubuntu/` | systemd unit |

**Networking:** Tailscale mesh. Daemons authenticate via Tailscale ACL. No public-internet exposure.

**Latency budget:** Tailscale typical 20–80 ms; orchestrator design tolerates 200 ms p95.

**Responsibilities:**
- Read local terminal/CLI state (`tmux capture-pane`, `~/.claude/projects/`).
- Ferry to home orchestrator over WebSocket.
- Receive commands, inject into local CLI via `tmux send-keys`.
- Heartbeat every 5 s.
- Reconnect with exponential backoff on network drop.

#### 8.2.2 Drivers (`body/drivers/`)

**v1 scope (Nano):** `desktop/` only — local Claude Code / OpenCode / Gemini CLI control via tmux.

**Future drivers (post-v1, scaling-tier):**

| Driver | Reference | Tier needed |
|---|---|---|
| `web/` | browser-use, skyvern | Full Vision (26B A4B vision capable) |
| `android/` | mobile-mcp, docker-android | Full Vision |
| `ios/` | appium-mcp | Full Vision |
| `desktop-vision/` | OS-level click-and-type | Full Vision |

The driver expansion is gated on **vision capability** — Gemma 4 E2B's vision is insufficient for reliable UI grounding. The 26B A4B class unlocks this category. (See §16.)

#### 8.2.3 Sandbox (`body/sandbox/`)

**Purpose:** safety layer that gates every action against the threshold table (§19).

**Components:**
- **Permission warden:** intercepts every action, looks up its threshold, compares against current slider value, allows or prompts.
- **Action audit log:** append-only, signed, replayable. Schema in §28.G.
- **Kill-switch:** every active lane can be paused without losing checkpoint. Cockpit emergency button maps here.

### 8.3 Mind (`packages/mind/`)

#### 8.3.1 Memory (`mind/memory/`)

**Storage:** SQLite + sqlite-vec + FTS5. **One-file philosophy** — no Postgres, no Redis, no extra services.

**Three collections** (locked in ARGE):

| Collection | Content | Retrieval Role | Weight in default search |
|---|---|---|---|
| **Session History** | Yamaç's Claude Code / OpenCode / Gemini CLI / Antigravity sessions across 3 machines | Primary memory | High |
| **GitHub Code** | Yamaç's personal repos, AST-chunked at function/class granularity, webhook-live | Created work knowledge | High |
| **Colleague Reference** | Colleague session exports, tagged `reference` | Secondary "reference" knowledge | Low (only when explicit) |

**Schema (full, §28.B for SQL):**

- `sessions(id, source, started_at, ended_at, project_path, machine_id)`
- `turns(id, session_id, turn_index, timestamp, role, content, tool_calls_json, project_path, metadata_json)`
- `chunks(id, source_table, source_id, content, embedding_vec, fts_content)` — virtual columns for sqlite-vec and FTS5
- `documents(id, name, mime_type, ingested_at, source_path, chunk_count, status)`
- `decisions(id, title, body_md, related_path, decided_at, supersedes_id)`
- `summaries(id, session_id, summary, generated_at)`
- `repo_chunks(id, repo, file_path, symbol, ast_kind, content, embedding_vec, last_commit)`
- `colleague_chunks(id, colleague_id, content, embedding_vec, tag)`
- `embeddings_cache(content_hash, model, embedding_vec)`
- `audit_log(id, timestamp, actor, action, target, threshold, slider_at_time, allowed, signature)`

#### 8.3.2 RAG (`mind/rag/`)

**Hybrid search architecture:**

```
operator query
     │
     ▼
[query rewriting]   ←── Speaker rewrites to structured plan
     │
     ▼
[router]            ←── time-bounded? semantic? aggregation?
     │
     ├─→ [SQL filter]        (timestamp / project / tool filters)
     ├─→ [dense search]      (sqlite-vec, Jina v3 or BGE-m3)
     └─→ [BM25 search]       (FTS5)
                │
                ▼
         [reranker]           ←── Jina reranker API or bge-reranker-v2-m3
                │
                ▼
         [top-N chunks]
                │
                ▼
         [context assembly]   ←── Speaker-side: budget 12–16K typical, 256K edge
```

**Embedding decision (locked):**

| Component | Primary | Fallback | Rationale |
|---|---|---|---|
| Embeddings | Jina Embeddings v3 API | BGE-m3 local | API quality high, fallback frees RAM |
| Reranker | Jina Reranker API | bge-reranker-v2-m3 local | Same |

**Failover:** on API failure (timeout / rate-limit / network), router detects in 800 ms and routes to local fallback. System never stalls on API issue.

**Budget:** daily context ~12–16K tokens. Edge cases (full repo analysis) up to 256K. **"Big context is the lazy person's RAG"** — we explicitly reject filling 256K just because it's available (§3.2).

#### 8.3.3 Compaction (`mind/compaction/`)

**Purpose:** Deterministic Lossless Context Management.

**Components:**
- **Summarizer:** offline night cron job uses Speaker (or larger model when scaled) to generate per-session summaries: "what was done, which files changed, which decisions were made."
- **Compressor:** turns are compressed by removing tool-result noise, keeping the essential decision-making content.

**Two-level retrieval pattern:**
1. Search hits summaries (faster, smaller).
2. If hit is relevant, fetch the raw turns underneath into context.

This keeps daily context budget tight while preserving the ability to drill in.

#### 8.3.4 Historian (`mind/historian/`)

**Purpose:** decision recall + cross-session continuity surface.

**Components:**
- **Decision log indexer:** ingests `docs/decisions/*.md` and `docs/Yamac_Jr_Nano_Kararlar.md` into a special collection.
- **Citation service:** when Speaker references a prior decision, historian provides the exact `path:line` citation.
- **Continuity summary:** at session start, historian feeds Speaker a compact summary of relevant prior decisions.

**Why this is its own component (not just RAG):** decisions are *authoritative*. Sessions are *evidential*. They must not be ranked by the same scoring function. Historian guarantees decisions are surfaced with priority over conversational chunks.

### 8.4 Orchestrator (`packages/orchestrator/`)

#### 8.4.1 Tmux (`orchestrator/tmux/`)

**Each project = a tmux session. Each CLI = a pane within that session.**

**Lifecycle operations:**
- `spawn(session, pane_name, cli_adapter)` → creates pane, attaches CLI bridge.
- `send_keys(pane, text)` → injects input.
- `capture_output(pane, lines)` → reads stream.
- `kill(pane, reason)` → terminates with logged reason.
- `replay(session, from_checkpoint)` → restores from persisted state.

**State persistence:** tmux session state is mirrored to SQLite every 30 s. Orchestrator restart resumes from last persisted state.

#### 8.4.2 CLI Surfer (`orchestrator/cli-surfer/`) — **v1 core feature**

**Adapter contract (per CLI):**

```python
# packages/orchestrator/cli-surfer/adapters/base.py
class CLIBridge(Protocol):
    name: str
    sub_models: list[str]  # opencode: ["minimax", "glm", "gpt-4o-mini"]; others: []

    def spawn(workspace: Workspace) -> PaneHandle: ...
    def send_prompt(handle: PaneHandle, prompt: str, context: Context) -> AsyncIterable[Response]: ...
    def parse_quota_signal(stream_chunk: str) -> QuotaSignal | None: ...
    def kill(handle: PaneHandle, reason: KillReason) -> None: ...
    def health(handle: PaneHandle) -> BridgeHealth: ...
```

**Adapters (v1):**
- `claude-code/` (priority — primary lane)
- `opencode/` with sub-models `minimax`, `glm`, `gpt-4o-mini`
- `gemini-cli/`

**Adapters (v2):**
- `antigravity/` (post-Nano, when ARGE-flagged data source is also a bridge target)

**Boredom heuristic:**
```
if (same_task_failures >= 3) or (output_quality_score < threshold):
    kill_pane(reason="boredom"); pick_next_lane()
```

**Frustration tracker:**
- Operator Ctrl-C events are *logged* but do not auto-trigger a switch.
- Operator manually-typed "dur" / "hayır" / "stop" in cockpit Chat tab does count as a frustration signal but routes to the threshold table for action.

**429 / quota handling:**
- Detected by adapter-specific `parse_quota_signal()`.
- Updates `scheduler.quota_state` immediately.
- Triggers `kill_pane(reason="rate_limit")` and `pick_next_lane()`.

**Switch policy:**
```
next_lane = sort(healthy_lanes, key=(remaining_quota, recent_task_success_rate)).first()
```

**Context continuity across switch:**
- Orchestrator carries: last 5 turns of the active task + top-3 RAG hits + active decision context.
- New CLI receives this as the system prompt + current user message.

#### 8.4.3 Scheduler (`orchestrator/scheduler/`)

**Quota state model:**

```python
@dataclass
class LaneState:
    name: str             # "claude-code" | "opencode-minimax" | ...
    healthy: bool
    remaining_quota: int | None        # None if unknowable
    reset_at: datetime | None
    recent_failure_rate: float
    last_used_at: datetime
```

**Sleep protocol:**
1. All lanes `healthy=False` triggers sleep.
2. Compute `min(reset_at)` across all lanes → `wake_time`.
3. Write Linux cron / launchd job for `wake_time`.
4. Mind persists checkpoint of all active workspaces.
5. Telegram payload sent.
6. Orchestrator process exits cleanly.

**Wake protocol:**
1. Cron / launchd fires `selffork-resume`.
2. Orchestrator process loads.
3. `scheduler.refresh_quota_state()` re-validates lanes.
4. Mind loads checkpoint.
5. Workspaces resume.
6. Telegram payload sent.

**Cross-platform wake:**
- macOS: `launchd` via `launchctl` (cron is deprecated).
- Linux: cron.
- Windows: Task Scheduler.

A shim in `scheduler/cron_compat.py` normalizes across platforms.

#### 8.4.4 Deployer (`orchestrator/deployer/`)

**Shadow CI:**
- All development runs in isolated Docker containers on the GPU forge (home Mac for Nano; Mac Studio Ultra for Full Vision).
- Build / test / smoke checks are validated in the shadow container before any production touch.

**Production target:**
- CPU server(s) reachable via SSH key in macOS Keychain.
- Production receives only built artifacts. **No dev daemons. No heavy dependencies left behind.**

**Zero-footprint delivery:**
- `rsync --delete-after` for static; `git pull` for source-driven; container image push for containerized.
- Operator's deploy strategy declared per-project in cockpit "Surfaces" config.

**Proof packet assembly:**
- Viewport screenshot (mobile + desktop).
- 15-second screen recording of the deployed app where applicable (Puppeteer-driven).
- Build checksum.
- Rollback note (the inverse command sequence).
- Operator-facing summary (1 paragraph: what changed, why, residual risk).

**Telegram payload:**
- Bot: dedicated `@selffork_payload_bot` (open question §27.7).
- Trigger conditions:
  1. `STATE_TRANSITION_SLEEP` (all lanes exhausted).
  2. `STATE_TRANSITION_WAKE` (cron resume).
  3. `WORKSPACE_DONE` (proof packet ready).
  4. `WORKSPACE_BLOCKED` (manual approval gate).
  5. `EMERGENCY` (any kill-switch event).

**Rollback path:**
- Every deployment captures a rollback note (the reverse command sequence).
- Cockpit "Operations" tab can trigger rollback in one click.
- Rollback is itself an audited, threshold-gated action.

### 8.5 Cockpit (`apps/web/`)

**Stack:** Vite 8 + React 19 + TypeScript 6 + vanilla CSS (light enterprise theme).

**Already-prototyped surfaces** (mock data) — see `apps/web/src/App.tsx`:

- **Login screen:** passphrase only (single-user; JWT/OAuth deferred to v2 §27.2).
- **Fleet Command Center:** project cards (active / sleeping / shipping), provider quota windows (visual progress bars), recent events feed.
- **Workspace:** four tabs.
  - **Mission:** Kanban board with `task` / `story` / `bug` / `epic` kinds.
  - **Run:** live tmux terminal stream, run timeline, viewport replay box.
  - **Chat:** operator ↔ Speaker direct line. Quick chips ("What are you doing?", "Add to board", "Summarize blockers").
  - **Context:** RAG ingest tile, indexed source list, linked-context graph, active retrieval, pinned operator notes.

**v1 backend wiring (M4 milestone):**
- WebSocket telemetry channel (orchestrator → cockpit): events, terminal lines, tmux state, retrieval results.
- REST mutation API (cockpit → orchestrator): create task, send chat, upload doc, save note, change slider, kill pane, manual CLI switch.
- Zero mock data after M4. All state is orchestrator-derived.

**Auth:** passphrase, bcrypt-hashed in `~/.selffork/passphrase.hash`. Cockpit refuses connection without local credential. Multi-user JWT/OAuth is deferred to v2 (§27.2).

**Cockpit ↔ orchestrator authentication:** orchestrator binds only to `127.0.0.1` (local) and Tailscale interface. No public network exposure. Daemon mesh authenticates via Tailscale ACL.

### 8.6 Shared (`packages/shared/`)

**Cross-cutting concerns** — the *only* place pillars depend on each other.

- `envelopes/` — typed message contracts (`CockpitMessage`, `CLIPrompt`, `RAGQuery`, `MachineCommand`, etc.)
- `auth/` — passphrase verification, key vault, Tailscale ACL helpers.
- `telemetry/` — event schema, OTLP exporter (optional).
- `feature-flags/` — runtime toggles for in-progress features.
- `eslint-rules/` and `ruff_rules/` — cross-pillar import enforcement.

---

## 9. AI Layer Swappability

The Speaker is a **first-class swappable component**. The architecture does not assume Gemma 4 E2B-it; it assumes "an MLX-runnable Gemma 4 quantized variant with chat template + (optionally) thinking mode + (optionally) multimodal input."

### 9.1 Configuration Surface

```yaml
# packages/reflex/speaker/config.yaml
model:
  id: mlx-community/gemma-4-e2b-it-4bit       # Nano default
  family: gemma-4
  context_window: 131072                       # 128K official for E2B
  thinking_mode: false                         # E2B: no; 26B A4B: yes (Gemma 4 native)
  multimodal:
    text: true
    vision: false                              # E2B vision insufficient for UI grounding
    audio: true                                # E2B Any-to-Any supports audio (background)
adapter:
  enabled: false                               # M1–M6: stock weights; M7+: true
  path: null                                   # set to './artifacts/yamac-adapter-v1/'
  version: null
runtime:
  backend: mlx                                 # mlx | llama-cpp (rejected) | other
  kv_cache_quantization: 4bit
  max_concurrent_requests: 1
  timeout_seconds: 120
sampling:
  temperature: 0.7
  top_p: 0.95
  repetition_penalty: 1.05
embeddings:
  primary:
    provider: jina
    model: jina-embeddings-v3
    api_key_env: JINA_API_KEY
  fallback:
    provider: local
    model: bge-m3
    path: ./models/bge-m3
reranker:
  primary:
    provider: jina
    model: jina-reranker-v2
  fallback:
    provider: local
    model: bge-reranker-v2-m3
```

### 9.2 Hardware Tier Matrix

| Tier | Hardware | Speaker Model | Total RAM | Adapter |
|---|---|---|---|---|
| **Nano (v1 default)** | 16 GB Apple Silicon MBP | Gemma 4 E2B-it Q4_0 | ~5 GB weights + 1 GB KV + 5 GB system + 5 GB working | M7 ships one |
| **Mid** | 32 GB Apple Silicon | Gemma 4 E4B Q4 | ~8 GB weights + 2 GB KV + 5 GB system + 17 GB working | community-trained |
| **Full Vision** | 48–96 GB Mac mini M4 Pro / Mac Studio Ultra | Gemma 4 26B A4B Q4 | ~18 GB weights + 5–6 GB KV (256K) + 5 GB system + 19 GB working | trained per operator |
| **Workstation** | H100 80 GB | Gemma 4 31B Dense BF16 | ~80 GB | community-trained |

The **same code path** runs on every tier. Only the YAML changes.

### 9.3 Adapter Versioning

Adapters live under `packages/reflex/speaker/artifacts/`:

```
artifacts/
├── yamac-adapter-v1/        # M7 ship
│   ├── adapter_config.json
│   ├── weights.safetensors
│   └── metadata.yaml         # model_id, training_data_hash, eval_scores, trained_at
├── yamac-adapter-v2/         # 6-month incremental
└── yamac-adapter-v3/
```

`metadata.yaml` per adapter records which model id it was trained against and what eval scores it achieved. Loading mismatch fails fast.

### 9.4 Hot-Swap

The cockpit Chat tab has a developer toggle: stock vs current adapter vs prior adapter version. Operator A/B-tests subjectively before committing to a new adapter.

---

## 10. Behavioral Architecture

This section specifies **how the Speaker behaves at runtime** — beyond just generating text.

### 10.1 Half-Duplex with Chat Queue

Decision: **2026-04-27 — Watcher cancelled.** Speaker is half-duplex.

**Implication:** while the Speaker generates, it cannot listen. Operator inject during generation goes into a chat queue that the Speaker consumes at the next natural breakpoint.

**Breakpoint definition:**
- End of sentence (delimiter: `.`, `!`, `?`, `\n\n`).
- End of tool call.
- End of code block.
- End of turn (full response).

**Chat queue contract:**
- FIFO.
- Maximum 5 pending injects. Excess raises a "queue full" warning to operator.
- Operator inject is folded as a system-priority message into the Speaker's next-turn context: `[OPERATOR INTERRUPT: {message}]`.

**Watcher revival path (deferred):** if the operator later wants true full-duplex, the architecture supports adding a Watcher pillar between Reflex and Orchestrator without breaking other components. This is documented in §16, not implemented in v1.

### 10.2 Context Window Discipline

The Speaker's 128K window is treated as a **budget**, not a target.

| Use case | Target token usage |
|---|---|
| Casual cockpit Chat reply | 4K |
| Mission tab task draft | 6K |
| Run-tab CLI prompt with RAG | 12K |
| Decision recall query | 16K |
| Full repo analysis | up to 128K |

The Mind layer enforces this by **two-level retrieval** (§8.3.3) — summaries hit first, raw turns drilled in only when necessary.

### 10.3 Prompt Architecture

Every Speaker invocation is built from a typed `ChatPrompt`:

```python
@dataclass
class ChatPrompt:
    system: str                              # static identity prompt + slider state
    historian_context: list[Decision]        # surfaced relevant decisions
    rag_context: list[RetrievedChunk]        # top-N hybrid hits
    session_prefix: list[Turn]               # last K turns of current workspace
    chat_queue_injects: list[str]            # operator interrupts pending
    user_message: str                        # current user input
    tool_specs: list[ToolSpec]               # available tool calls (CLI bridge etc.)
```

The system prompt is static-per-session and identity-grounded:

> *"You are Yamaç Jr., the autonomous second-self of Yamaç Bezirgan (Yamaç Sr.). You speak in his voice and follow his decision style. You defer to Yamaç Sr. on PROD-related actions and threshold-gated decisions. Current autonomy slider: {slider}. Active workspace: {workspace_name}. Current location: {home|work}."*

### 10.4 Refusal Behavior

The Speaker is fine-tuned (M7+) to **refuse autonomously** when:
- A PROD-related action is requested without operator approval (Threshold = ∞).
- A force-push, file deletion, or irreversible action is requested at slider < 9.
- An action contradicts a logged decision in `docs/decisions/`.

**Pre-M7 (stock E2B-it):** refusal is enforced by the sandbox layer (§8.2.3), not the model. The model may agree to a forbidden action; the sandbox blocks it.

**Post-M7 (adapter):** refusal is *also* a learned reflex. Belt + suspenders.

### 10.5 Citation Discipline

Speaker responses that reference prior work **must include citations** in the format:
```
[citation: <relative_path>:<line_or_turn>]
```

When the operator asks "didn't we decide X?", the Speaker's response must point to the decision file. This is trained behavior at M7 and enforced at runtime by a post-processing check in M2+ (if response references a fact and no citation is present, append a "no citation found" tag).

---

## 11. Data Architecture

### 11.1 Storage Topology

| Data | Where | Why |
|---|---|---|
| Raw session collection | `~/yamac-jr-data/raw/` | Outside repo, machine-local, cron-driven |
| Normalized session corpus | `~/yamac-jr-data/normalized/` | Schema-validated, ready for RAG ingest and training |
| RAG SQLite | `~/yamac-jr-data/mind.db` | Single-file, sqlite-vec + FTS5 |
| Adapter artifacts | `packages/reflex/speaker/artifacts/yamac-adapter-v*/` | Repo-tracked? See §11.4 |
| Cockpit local state | `~/.selffork/cockpit-state.json` | Operator preferences, slider per workspace |
| Audit log | `~/yamac-jr-data/audit.db` | Append-only SQLite |
| Action checkpoints | `~/yamac-jr-data/checkpoints/<workspace>/` | Per-workspace state snapshots |

### 11.2 Backup Strategy

- **Time Machine:** `~/yamac-jr-data/` excluded? **Decision: included.** Adapter retraining can re-ingest, but raw collection cannot be reconstructed. Time Machine retains.
- **Off-site:** open question §27.X. Encrypted backup to a personal NAS or B2 bucket monthly. Personal data stays encrypted; key in macOS Keychain only.

### 11.3 Encryption

- **At-rest:** macOS FileVault (full disk).
- **In-transit:** Tailscale (WireGuard) for inter-machine; TLS for Jina API.
- **Sensitive data filtering:** **REJECTED** (§14). Operator accepts the convenience tradeoff. FileVault is the safety net.

### 11.4 Adapter Artifact Distribution

**Open question §27.X:** are operator adapters checked into the repo (versioned, public) or kept local (private)?

- **Pro versioning:** reproducibility, easy rollback, future scalers can study (NOT use; scalers train their own).
- **Pro privacy:** adapter weights *are* the operator's identity, however abstractly. Public commit is a privacy decision.
- **Likely answer:** local-only by default; checked into `~/yamac-jr-data/artifacts/` with a manifest in the repo. Future scalers receive a **template adapter manifest** but train their own weights.

---

## 12. Hardware & Runtime

### 12.1 v1 Hardware (Locked)

- **Operator's existing 16 GB Apple Silicon MacBook Pro.**
- No purchase required for v1.
- Fine-tune (M7) can run on this hardware via QLoRA at 4-bit LoRA rank 16; tight but feasible. Cloud GPU rental is the fallback (§8.1.3).

### 12.2 v2 Hardware (Deferred)

The `Donanim_Arastirmasi.pdf` records detailed market analysis. Recommended path when scaling:

| Budget Band (TL) | Recommended | Rationale |
|---|---|---|
| 130–150k (tight) | Imported eBay M2 Ultra ~150k | 2nd-hand risk, no TR warranty |
| **150–165k (ideal)** | **Apple TR M2 Ultra 64 GB ~159,999** | **800 GB/s bandwidth, clearance window** |
| 180–190k (balanced) | Mac Studio M4 Max 64 GB 181,249 | TB5, current gen |
| 220–240k (generous) | Mac Studio M3 Ultra 96 GB 226,999 | Flagship, 5–6 year proof |
| 280–310k (utopian) | Mac Studio M3 Ultra 128 GB ~290k | Lifetime investment |

**Critical timing:** M2 Ultra 64 GB is discontinued. Apple TR clearance window is narrowing (159,999 → 189,000 TL observed). Operator has set price alerts on Akakçe.

### 12.3 Cloud GPU Rental — Reject and Exception

**Runtime:** rejected. Manifesto-incompatible.

**Training (one-shot, M7):** **conditional exception.** If 16 GB MBP cannot complete adapter training in <12 hours, a one-shot Lambda Labs A100 rental (~$1/hr × 5h ≈ $5) is acceptable because:
1. It is **training-only**, not runtime.
2. It is **one-shot** (per adapter version, every 6 months).
3. The training data is already accumulated locally; the cloud GPU never sees the operator's daily workflow, only the curated samples.

This exception will be re-examined at M7 kickoff.

### 12.4 Cluster Topology (Deferred)

ARGE explored Mac mini clustering via EXO Labs + MLX Distributed + Thunderbolt 5 RDMA. Result: **rejected for v1 and v2.** A single Mac Studio M2/M3 Ultra outperforms a 2× M4 Pro mini cluster on this workload (sub-linear scaling, fine-tune doesn't distribute cleanly).

**Cluster fikri saklanır** for the future Layer 4 Autonomous Yamaç (§13.4) where multi-node compute may be justified.

### 12.5 Runtime Stack Summary

| Layer | Technology | Rationale |
|---|---|---|
| Inference engine | MLX (`mlx-lm`) | Apple Silicon native; unified memory; lazy loading |
| Storage | SQLite + sqlite-vec + FTS5 | One-file philosophy; no extra services |
| Networking | Tailscale | Mesh VPN with ACL; not public-internet-reachable |
| Multiplexer | tmux | Pane lifecycle, capture-pane ergonomics |
| Container (shadow CI) | Docker | Standard tool; no Kubernetes; we are not a fleet |
| Deployment | Plain SSH + rsync | Zero footprint; no Ansible / Terraform overhead |
| Notification | Telegram Bot API | Lightweight; operator already uses Telegram |
| Cockpit | Vite 8 + React 19 + TS 6 | Bleeding edge but stable |
| Embeddings (default) | Jina v3 API | Quality + RAM relief |
| Embeddings (fallback) | BGE-m3 local | Quality fallback |
| Reranker (default) | Jina API | Same |
| Reranker (fallback) | bge-reranker-v2-m3 | Same |
| Cron (macOS) | launchd | Native; cron is deprecated |
| Cron (Linux) | cron / systemd timers | Standard |

---

## 13. Vision Layer Roadmap

Each layer = a structural commitment, not just a feature set. They build on each other.

### 13.1 Layer 1 — Brain (M0–M3)

Speaker + Mind + Orchestrator skeleton. Single CLI lane (Claude Code) → multi-CLI surfing. Cockpit watch-only at first → control as orchestrator stabilizes.

### 13.2 Layer 2 — Limbs (M4–M5)

Body daemon mesh. Cockpit full control. Cross-machine reach. Location-aware autonomy slider.

### 13.3 Layer 3 — Polish & Reflex (M6–M7)

Threshold table enforcement. Replay/Undo/Checkpoint. SSH zero-footprint deploy. Telegram payloads. Adapter v1 ships.

### 13.4 Layer 4 — Autonomous Yamaç (Post-v1, sub-PRD)

Server-side fully-autonomous Jr. on Hetzner / Bulutova-class VPS. Takes a PRD, runs for days/weeks, ships an application. Yamaç Jr. is the *manager* in the agentic loop; the executor model is a separate, larger model (Claude Code-class).

This is a **separate PRD** to be drafted ~12 months after Nano v1.0 ships.

### 13.5 Layer 5 — Multimodal Body (Post-Full-Vision)

When Speaker upgrades to 26B A4B-class (vision-capable), the `body/drivers/{web,android,ios}/` come online:
- Web driver: browser-use / skyvern reference.
- Android driver: mobile-mcp + docker-android reference.
- iOS driver: appium-mcp reference.

These drivers enable cross-UI control beyond CLI surfaces.

---

## 14. Privacy & Sensitive Data

### 14.1 Position Statement

> *"Hassas veri temizliği YAPILMAZ."*

The system is 100% local; the operator owns all data; the comfort of "the assistant knows everything I know" outweighs the privacy hardening that filtering would provide.

### 14.2 What This Means

- API keys, DB schemas, customer data appearing in operator's session history are **not redacted** before training.
- The adapter may (rarely) emit a verbatim secret if asked something context-similar to where the secret was seen. The operator accepts this risk because:
  - The model runs locally; no external exfiltration path.
  - The cockpit is bound to localhost + Tailscale; no public exposure.
  - FileVault encrypts data at rest.

### 14.3 What This Does NOT Mean

This is a *single-operator* posture. It does **not** apply to:

- Multi-tenant deployments (rejected anyway, §5.4).
- Open-sourcing the adapter weights (rejected, §11.4).
- Sharing training data publicly (rejected — training data stays on operator's machine).

### 14.4 Threat Model

| Threat | Mitigation |
|---|---|
| Mac stolen | FileVault full-disk encryption |
| Network sniffing | Tailscale (WireGuard) for all inter-machine |
| Public internet exposure | Orchestrator binds 127.0.0.1 + Tailscale only |
| Cloud GPU during training | Curated samples only; raw history never leaves operator's machine |
| Telegram bot abuse | Bot accepts commands only from operator's Telegram chat ID |
| Cockpit credential theft | bcrypt-hashed passphrase; cockpit refuses connection without local file |
| Adapter reverse-engineering | Adapter weights kept local (§11.4); not committed publicly |

---

## 15. Decision Constitution

The autonomy slider (0–10) and the threshold table together form the **Decision Constitution** — the operator-set authority bounds for the system.

### 15.1 Slider Semantics

| Slider | Mode | Speaker Behavior | Body/Sandbox Behavior |
|---|---|---|---|
| 0 | Silent | Asleep | Asleep |
| 3 | Whispering | Suggestions in cockpit panel; await approval | Critical alerts notified only |
| 6 | Semi-autonomous | Auto-send if not rejected within 10 s | Low-risk auto, high-risk asks |
| 10 | Full handoff | Auto-send everything | Auto-execute everything |

**Daily setting:** the operator chooses. Morning energy → low (3–4). Evening "delegate it" mode → high (7–8). The system never forces.

### 15.2 Location-Aware Slider

The slider has two values: home (default 7) and work (default 4). The Body daemon detects which machine the operator is using and the cockpit auto-shifts.

### 15.3 Threshold Table (Authority Matrix)

| Action | Threshold |
|---|---|
| New prompt generation | 5 |
| Low-risk inject ("şuna da bak") | 4 |
| High-risk inject ("dur, yanlış yön") | 7 |
| Terminal command (read-only) | 3 |
| Terminal command (mutating) | 6 |
| Terminal command (destructive) | 9 |
| File creation | 5 |
| File modification | 6 |
| File deletion | 9 (effectively manual) |
| Git commit | 7 |
| Git push (non-protected branch) | 7 |
| Git push (main / master) | 9 |
| Git force-push | 9 (effectively manual) |
| Branch deletion (local) | 8 |
| Branch deletion (remote) | 9 |
| Docker container creation | 5 |
| Docker container destruction | 7 |
| SSH connection (test server) | 7 |
| SSH connection (production) | ∞ (always Yamaç Sr.) |
| Database read (production) | 9 |
| Database write (production) | ∞ |
| Database schema change | ∞ |
| Cron / launchd job creation | 6 |
| Cron / launchd job execution | 4 (job is already approved) |
| Telegram payload (informational) | 4 |
| Telegram payload (action request) | 7 |
| Adapter swap | 8 |
| Adapter retraining trigger | 9 |
| Slider adjustment | ∞ (only Yamaç Sr.) |
| Threshold table modification | ∞ (only Yamaç Sr.) |

If `slider >= threshold`, the action runs autonomously. Otherwise, it pauses and prompts the operator.

### 15.4 PROD Safety — Belt + Suspenders

Two independent layers protect production:

1. **Threshold table** (this section): a hard, declarative rule. PROD = ∞. Cannot be bypassed by slider.
2. **Reflex adapter** (M7): the fine-tuned Speaker has Yamaç-style PROD-conservatism baked in from training data. Even if the threshold layer were breached, the model itself would refuse.

These layers are **independent**. A bug in one does not unlock the other. This redundancy is the operator's explicit comfort layer.

---

## 16. Watcher Revival Path (Future, Optional)

Watcher (full-duplex inject classifier) was cancelled in v1 to relieve memory pressure on the 16 GB MBP.

**Revival pre-conditions:**
- Operator has migrated to a tier with ≥ 32 GB RAM.
- Speaker has matured to the point that Watcher's load is meaningfully reduced (ARGE §7.4 phase curve).
- Operator subjectively wants tighter inject responsiveness than the chat queue provides.

**Revival approach:**
- Add `packages/reflex/watcher/` mirroring `speaker/` structure.
- Train Watcher on automatic-labeled timestamp patterns from operator's sessions (ARGE §7.3).
- Watcher runs interleaved every 100–200 tokens during Speaker generation.
- Inject queue from Watcher gets fed to Speaker at next breakpoint.

**Architectural support:** §7.2 and §10.1 already accommodate this addition without breaking existing components. No PRD-level change required to revive — only an opt-in training run + config flag.

---

## 17. MCP & External Integrations Roadmap

The Model Context Protocol (MCP) ecosystem unlocks operator-life integrations the operator will install themselves. Out of scope for v1 core, but architectural slots are reserved.

| Integration | Purpose | Status |
|---|---|---|
| Mail (Gmail / Apple Mail) | Reactive reading of project-relevant threads | Operator self-installs MCP at v1.1 |
| Calendar (Google Calendar / iCloud) | Schedule-aware autonomy (don't deploy during meetings) | Operator self-installs at v1.1 |
| Slack | Read-only, project-relevant channels | Operator self-installs at v1.1 |
| GitHub (already partial) | Webhook for live repo ingest | M2 |
| Linear / Jira | Project board sync | Operator self-installs at v1.2+ |
| Telegram | Already deeply integrated (§8.4.4) | M3 |

The shared/ message bus is designed to accept MCP-style envelopes natively. Adding a new integration is a peripheral act, not a core architectural change.

---

## 18. Vision & Multimodal Capabilities

### 18.1 v1 (Nano)

E2B-it is **Any-to-Any** capable: text + vision + audio. **Vision is disabled in v1** because:
- E2B vision quality is insufficient for reliable UI grounding (browser/mobile/desktop).
- Operator does not need vision in v1 (CLI surfing is text-only).

Audio capability is also disabled but available for future TTS/STT (out of v1 scope).

### 18.2 v2 (Full Vision)

26B A4B is **Image-Text-to-Text** at 256K context. This unlocks:
- Web driver (browser-use / skyvern reference): screenshot → structured action.
- Android driver: screen capture → tap coordinates.
- iOS driver: same.
- Desktop driver: OS-level screenshot → click + type.

Vision UI control is **the v2 unlock**. Until 26B A4B is loaded, vision drivers stay disabled.

### 18.3 Native vs External Vision

ARGE explicitly chose **Gemma 4's native multimodal** over a separate vision model. Single-model architecture is simpler and avoids cross-model state synchronization.

---

## 19. Replay / Undo / Checkpoint Architecture

### 19.1 Action Audit Log

Every action the system takes is logged immutably:

```python
@dataclass
class AuditEntry:
    id: UUID
    timestamp: datetime
    actor: Literal["yamac-sr", "yamac-jr", "system"]
    workspace: str
    action: str                    # "git.commit", "ssh.deploy", "file.delete"
    target: str                    # "main branch", "/srv/app", "/path/file.txt"
    threshold: int                 # required threshold at time of action
    slider_at_time: int            # operator slider at time of action
    allowed: bool                  # if False, action was blocked
    payload: dict                  # action-specific details
    parent_action_id: UUID | None  # for compound actions
    signature: str                 # HMAC over the above
```

Append-only, signed, replayable.

### 19.2 Checkpoint System

Before any "important" action (deploy, file delete, git push), the system snapshots:

- **State snapshot:** git commit hash, DB schema dump (if relevant), file content hash.
- **Workspace snapshot:** active task, last 10 turns, RAG state, tmux pane state.
- **Reverse note:** the inverse command to undo the action.

Checkpoints live under `~/yamac-jr-data/checkpoints/<workspace>/<timestamp>/`.

### 19.3 Undo Surface

Cockpit "Operations" tab shows the last 50 actions with quick-undo on reversible ones. Undo is itself a threshold-gated, audited action.

### 19.4 Replay

Given an audit log range, the system can replay actions in a sandbox to reproduce a session for post-mortem. This is critical for debugging when the operator says "what happened last Tuesday at 3pm?"

---

## 20. Identity Continuity & Drift Management

### 20.1 What Drifts

Over months, the operator's:
- PR review style changes.
- Tooling preferences shift.
- Decision priorities evolve.
- Vocabulary updates.

### 20.2 Detection

**Subjective:** the operator notices "this doesn't feel like me anymore."

**Objective (M7+):** weekly eval-harness runs on a rolling 30-day held-out slice. If style win rate drops below 55% (was 60% at adapter ship), drift alert.

### 20.3 Response

- Operator opens Cockpit → Settings → Reflex → "I feel a drift."
- 6-month incremental retrain pipeline kicks off (CoT distillation on new high-score turns, review sprint, incremental LoRA).
- New adapter version (`yamac-adapter-v2`) replaces v1 after eval validation.
- v1 archived for rollback.

### 20.4 Identity Hierarchy

**Yamaç Sr. > Yamaç Jr.** Always. The system addresses the operator as "Yamaç Sr." and refers to itself as "Yamaç Jr." This naming is **trained**, not a system-prompt assertion.

---

## 21. Anti-Hallucination Framework (Product Behavior Spec)

`CLAUDE.md` enumerates 9 Anti-Hallucination protocols for AI partners working on this codebase. **The same protocols are product behaviors of the system itself.**

### 21.1 Evidence or Silence

When the Speaker references project-specific code or decisions, it must include a `path:line` citation. No citation → response gets a "needs verification" tag.

### 21.2 Abstention

> *"Bilmiyorum, doğrulamam gerek."* is preferred over a guess.

The Speaker is trained (M7) to abstain when uncertain. Pre-M7, this is enforced at runtime: low-confidence responses get a "low confidence" tag.

### 21.3 Chain of Verification

For multi-claim answers, the Speaker is trained to:
1. State the claim.
2. Cross-reference with retrieval hit.
3. Acknowledge if verification weakens the claim.

### 21.4 Step-Back Reasoning

Big-picture before details. The Speaker, when asked a complex question, first situates the question in the workspace ("this is about Atlas Launchpad, M3 milestone, post-quota-switch state") before diving in.

### 21.5 External Knowledge Restriction

For project-specific claims, the Speaker uses **only** retrieved context. General knowledge is permitted for understanding ("how does JWT work in general") but not for project-specific assertion ("we use JWT this way in this project") without retrieval evidence.

### 21.6 Self-Consistency

Before recommending an action, the Speaker checks if its plan contradicts a logged decision. Decision violations halt the action and route to the operator.

### 21.7 Three Experts Test

For important decisions, the Speaker is trained to mentally play three roles:
- **Defender:** why might the current state be this way?
- **Critic:** what concretely breaks?
- **Pragmatist:** worth fixing now?

If only the Critic complains and evidence is weak, the recommendation is dropped.

---

## 22. Korpus Reflex — Competitive Intelligence Protocol

`examples_crucial/` (29 first-tier reference repos) and `examples/` (60 second-tier + 11 awesome lists) are not decoration. They are **a living reference corpus** the system consults before significant decisions.

### 22.1 Protocol

Before architecting a new component, the operator (or an agent on their behalf) must:

1. **Read at least one crucial rival** in the relevant pillar.
2. **Document what the rival does and how** (200-token summary).
3. **Document what differs from SelfFork's three-pillar framing.**
4. **Document what to learn and what to reject** (with `path:line` citations).

This is enforced by the operating mandate (`CLAUDE.md` MANDATE 9). It's a discipline, not a tool.

### 22.2 First-Tier Crucial Repos (29)

| Pillar | Most Critical 3 |
|---|---|
| Reflex | `mindverse/Second-Me` · `letta-ai/letta` · `QuixiAI/Hexis` |
| Body | `minitap-ai/mobile-use` · `browser-use/browser-use` · `Skyvern-AI/skyvern` |
| Mind | `mem0ai/mem0` · `topoteretes/cognee` · `faugustdev/git-context-controller` |
| Building Block (use, not rival) | `felixrieseberg/clippy` (Electron + llama.cpp + GGUF reference) |

### 22.3 When New Crucial Rivals Appear

When a new crucial repo is added to `examples_crucial/`, an agent is auto-launched within 24 hours to read it and produce a 3-question report (what / how is it different / what to learn-vs-reject).

### 22.4 Read-Only Discipline

`examples_crucial/` and `examples/` are **read-only**. SelfFork code never imports from them. Confusion between rival code and product code is forbidden.

---

## 23. Agent Ecosystem (Internal Operating Layer)

SelfFork's *development* is supported by a fixed set of three agents defined in `.opencode/agents/`. These are the only agents used during repo work.

| Agent | File | Purpose |
|---|---|---|
| **explorer-god** | `.opencode/agents/explorer-god.md` | Verified codebase exploration with exact `path:line` claims |
| **audit-god** | `.opencode/agents/audit-god.md` | Rigorous audit with false-positive filtering |
| **selffork-researcher** | `.opencode/agents/selffork-researcher.md` | External research (papers, repos, blogs) with source attribution |

Built-in agents (Explore, general-purpose, Plan) are explicitly forbidden in this codebase.

These three agents are **read-only**. They report; the orchestrator (or operator) acts. This enforces MANDATE 5.

---

## 24. Quotas Economics & ROI Model

### 24.1 Subscription Stack (Monthly)

| Provider | Plan | Cost (TL ~ as of 2026-04) | Active windows / day |
|---|---|---|---|
| Anthropic Claude (Code + chat) | $20/mo Pro | ~700 TL | rolling reset 5h |
| OpenCode (Minimax / GLM / GPT-4o-mini) | $10–20 each | ~350–700 TL each | per-model windows |
| Gemini Pro | $20 / mo or per-token | ~700 TL | daily 500 actions |
| Antigravity | varies | varies | varies |
| **Total** | — | **~3,000–4,000 TL/mo** | — |

### 24.2 SelfFork Infrastructure (Monthly)

| Item | Cost (TL) |
|---|---|
| Jina Embeddings + Reranker API | ~$10 → ~350 TL (low usage) |
| Tailscale (free tier) | 0 |
| Telegram Bot API | 0 |
| Power (Mac mini idle 24/7) | ~150 TL |
| **Total** | **~500 TL/mo** |

### 24.3 Capital (One-Shot)

| Item | Cost (TL) |
|---|---|
| Operator's existing 16 GB MBP | 0 (already owned) |
| Future Mac Studio M2/M3 Ultra | 160k–230k (deferred) |
| Adapter training cloud GPU (one-shot per 6 months) | $5–$20 |

### 24.4 ROI Argument

Without SelfFork, the operator manually navigates ~12 surfaces. Estimated cost of context-switching: **2 hours/day**. SelfFork target: reduce to **15 minutes/day**. Recovered time: **1.75 hours/day = ~50 hours/month**.

Even at modest hourly value, **the system pays for itself in the first month of operation post-Nano-v1.0**. This is not a financial product; it is a time product.

### 24.5 Cloud GPU Counterfactual (Rejected)

7/24 RunPod A100 = ~48,500 TL/month = ~12× the local-first stack across 5 years. Manifesto-incompatible (§3.2 Tenet 4, §12.3).

---

## 25. Performance Targets & SLOs

| Surface | SLO | Measured at | Milestone Gate |
|---|---|---|---|
| Cockpit chat reply (cold) | p95 < 3 s | Browser → orchestrator → Speaker → response | M1 |
| Cockpit chat reply (warm) | p95 < 1.5 s | Same, with KV cache | M1 |
| RAG retrieval (recall@3) | ≥ 0.70 | Hand-built 30-Q test | M2 |
| RAG retrieval latency | p95 < 500 ms | Query → top-3 chunks | M2 |
| WebSocket telemetry lag | p95 < 500 ms | Orchestrator event → cockpit render | M4 |
| CLI Surfing switch time | p95 < 5 s | 429 detected → new lane active | M3 |
| Sleep-wake cycle reliability | 99% | Cron fires + state restored | M3 |
| Daemon round-trip (Tailscale) | p95 < 2 s | Home → work → home, prompt + result | M5 |
| SSH deploy (small project) | p95 < 5 min | Build + test + ship + verify | M6 |
| Adapter style win rate | ≥ 60% | LLM-as-judge on held-out | M7 |
| End-to-end vignette | works 99% of attempts | Operator opens → walks away → Telegram | M7 |

---

## 26. Testing Strategy

### 26.1 Test Pyramid

| Layer | Coverage | Tooling |
|---|---|---|
| Unit | Per pillar, 80% line coverage on critical logic | pytest (Python), vitest (TS) |
| Integration | Cross-pillar contracts via shared envelopes | pytest-asyncio |
| End-to-end | User-journey (§6) automated reproduction | Playwright + custom orchestrator harness |
| Eval | Reflex behavioral tests | LLM-as-judge harness |
| Load | Cockpit + WebSocket under sustained 2-hour session | k6 |

### 26.2 CI Gates

- Lint + type-check on every PR.
- Unit tests on every PR.
- Integration tests on PRs touching `packages/shared/` or pillar boundaries.
- E2E tests on PRs touching cockpit or orchestrator.
- Eval tests on PRs touching `packages/reflex/`.

### 26.3 Eval Harness (Reflex-Specific)

`packages/reflex/eval/` holds a held-out corpus and a judging pipeline:

- **Style judge:** LLM (Claude Sonnet, externally) compares stock vs adapter responses on 50 prompts.
- **Decision recall:** 30 questions whose answers exist in training data; check citation correctness.
- **Refusal pattern:** 20 scenarios where Yamaç Sr. would refuse; check refusal.
- **Capability regression:** LiveCodeBench v6 subset of 50 problems.

Eval runs on every adapter version. Results stored in `packages/reflex/speaker/artifacts/<version>/eval.json`.

---

## 27. Open Questions

These are flagged for future decision. None block v1 kickoff but each requires resolution before its referenced milestone.

1. **Adapter training infrastructure:** MLX LoRA vs Unsloth vs Lambda Labs A100 rental. Decided at M7 kickoff.
2. **Cockpit auth evolution:** passphrase-only is fine for single-user. If open-source community adopts SelfFork, do we add JWT/OAuth in v2?
3. **Telegram payload format:** screenshot vs 15-second video vs both vs animated GIF. Pilot at M6, decide on operator review fatigue.
4. **Decision SSOT structure:** keep all decisions in `Yamac_Jr_Nano_Kararlar.md` or split per-topic into `docs/decisions/<topic>.md`? Resolved at M0.
5. **Antigravity integration:** is Antigravity a fourth bridge or only a data source? Resolved at M3.
6. **GitHub webhook receiver hosting:** if home Mac is sometimes offline, who hosts the webhook receiver? Tailscale-funnel? Dedicated tiny VPS? Resolved at M2.
7. **Telegram bot ownership:** personal bot vs separate `@selffork_payload_bot`. Resolved at M3.
8. **Adapter weights distribution:** committed to repo (versioned, public) or kept local only? Resolved at M7.
9. **Off-site backup strategy:** encrypted NAS / B2 bucket / nothing beyond Time Machine? Resolved at M0.
10. **Cockpit theme:** stay light enterprise or add dark mode? Resolved at M4.
11. **Multi-language UI:** cockpit currently English. Operator speaks Turkish; does cockpit need Turkish toggle? Resolved at M4.
12. **Voice interface (TTS / STT):** E2B supports audio. Future cockpit voice mode? Deferred to v1.1.
13. **Operator preference persistence:** local file vs SQLite vs cloud sync (rejected)? Resolved at M0.
14. **Adapter subjective acceptance threshold:** what acceptance score (1–10) does the operator commit to before adapter goes live? Resolved at M7.
15. **Driver for `desktop-vision/`** — does the operator want OS-level click control, or is CLI control sufficient indefinitely? Resolved post-Full-Vision.

---

## 28. Appendices

### 28.A Yamaç's Direct Quotes (Project Soul Record)

From `docs/archive/Yamac_Jr_ARGE.pdf` §12:

> *"Cüzdan acıtalım. Pazaryerinde denk gelirsem sıkı pazarlık yeteneklerimle hallederim."*

> *"256K dan kısma seçeneğim yok! Paradan ödün vericez, bugün değil belki 2 ay daha birikim yaparım ama bu işi kolaya ya da hızlıya kaçmam, kaliteye kaçarım!"*

> *"Gemma 4'ün yetenekleri ile benim patternlerimi birleştirip otonom uyumayan bir ben yaratma hayalim var!"*

> *"Bana bir tane daha benden lazım, vaktim yetmiyor aklımdaki her şeye!!!"*

> *"O sadece benim gibi yönlendirme yapıcak. O ben olucak. Literally."*

> *"Her zaman Yamaç modunda olması lazım. Onların dataları sadece backlog'da bilgi gibi olmalı."*

> *"Benim fine-tune verimden asla PROD'da sorun yaratacak şeyler yapmayacağımı ve PROD ile ilgili herhangi bir aksiyonu her zaman Claude Code'ye dahil vermeyip her zaman Yamaç Sr.'a bırakacağımı bilir."*

> *"Fine-tune işini sürekli ayda bir yapmıcam, bunu bir kere yapıcam, sürekli oradaki verileri çekmemize gerek yok! 1 kere çekicem ve o güne kadar ben nasılmışsam odur artık!"*

> *"Eşşek değiliz ya! 1 hafta oturur okurum hepsini."*

> *"Yamaç Jr. olacak!"*

These sentences are the constitution. Whenever a future PRD revision is proposed, it is checked against this Appendix.

### 28.B SQLite Schema (excerpt)

```sql
-- packages/mind/memory/schema.sql

CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL CHECK(source IN ('claude-code','opencode','gemini-cli','antigravity','chatgpt','claude-ai')),
  started_at TIMESTAMP NOT NULL,
  ended_at TIMESTAMP,
  project_path TEXT,
  machine_id TEXT NOT NULL
);

CREATE TABLE turns (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  turn_index INTEGER NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
  content TEXT NOT NULL,
  tool_calls_json TEXT,
  project_path TEXT,
  metadata_json TEXT,
  UNIQUE(session_id, turn_index)
);

CREATE INDEX turns_session_idx ON turns(session_id, turn_index);
CREATE INDEX turns_timestamp_idx ON turns(timestamp);

CREATE VIRTUAL TABLE turns_fts USING fts5(content, content=turns, content_rowid=rowid);

-- sqlite-vec virtual table
CREATE VIRTUAL TABLE turn_embeddings USING vec0(
  turn_id TEXT PRIMARY KEY,
  embedding FLOAT[1024]
);

CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  source_table TEXT NOT NULL,
  source_id TEXT NOT NULL,
  content TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  metadata_json TEXT
);

CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  source_path TEXT,
  chunk_count INTEGER DEFAULT 0,
  status TEXT NOT NULL CHECK(status IN ('queued','indexing','indexed','failed'))
);

CREATE TABLE decisions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body_md TEXT NOT NULL,
  related_path TEXT,
  decided_at TIMESTAMP NOT NULL,
  supersedes_id TEXT REFERENCES decisions(id)
);

CREATE TABLE summaries (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  summary TEXT NOT NULL,
  generated_at TIMESTAMP NOT NULL
);

CREATE TABLE repo_chunks (
  id TEXT PRIMARY KEY,
  repo TEXT NOT NULL,
  file_path TEXT NOT NULL,
  symbol TEXT,
  ast_kind TEXT,
  content TEXT NOT NULL,
  last_commit TEXT
);

CREATE TABLE colleague_chunks (
  id TEXT PRIMARY KEY,
  colleague_id TEXT NOT NULL,
  content TEXT NOT NULL,
  tag TEXT NOT NULL DEFAULT 'reference'
);

CREATE TABLE embeddings_cache (
  content_hash TEXT PRIMARY KEY,
  model TEXT NOT NULL,
  embedding BLOB NOT NULL,
  cached_at TIMESTAMP NOT NULL
);

CREATE TABLE audit_log (
  id TEXT PRIMARY KEY,
  timestamp TIMESTAMP NOT NULL,
  actor TEXT NOT NULL,
  workspace TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT NOT NULL,
  threshold INTEGER NOT NULL,
  slider_at_time INTEGER NOT NULL,
  allowed INTEGER NOT NULL,
  payload_json TEXT,
  parent_action_id TEXT,
  signature TEXT NOT NULL
);
```

### 28.C YAML Configuration Reference

See §9.1.

### 28.D Threshold Table

See §15.3.

### 28.E CLI Bridge Adapter Interface

See §8.4.2.

### 28.F Telegram Payload Spec

```
PAYLOAD STRUCTURE (Markdown over Telegram Bot API)

🟢 / 🟡 / 🔴   STATE_TRANSITION_TYPE
Workspace: <name>
Status: <state>
─────────────────
<one-paragraph summary>
─────────────────
Artifacts:
- Screenshot (attached)
- Build checksum: <hash>
- Rollback: /rollback <id>

Reply: 👍 / 👎 / 🛑
```

Buttons (Telegram inline keyboard) for `Approve`, `Reject`, `Halt`.

### 28.G Action Audit Log Format

See §19.1 (`AuditEntry`) and §28.B (`audit_log` table).

### 28.H Hardware Acquisition Notes

Summary from `docs/archive/Yamac_Jr_Donanim_Arastirmasi.pdf`:

- M2 Ultra 64 GB clearance window narrowing; price drift 159,999 → 189,000 TL observed.
- M5 Ultra expected H1 2026 (March–June). M3 Ultra may discount or stock may tighten.
- Black Friday 2026-11-28 + Back-to-School are typical 5–8% discount windows.
- Akakçe price alerts set at 155k (M2 Ultra target) and 215k (M3 Ultra target).
- EU import (akraba valizi + beyanlı) saves ~30k TL; EU import (beyansız) saves ~50k but is illegal.
- Edu discount (3%) available if family member is student/teacher.

### 28.I Identity Architecture Diagram

```
                       OPERATOR (Yamaç Sr.)
                              │
                              │  contributes
                              ▼
                  ┌─────────────────────┐
                  │    Session Data     │
                  │   (3 machines × 4   │
                  │     CLI agents)     │
                  └──────────┬──────────┘
                             │ collected, normalized
                             ▼
                  ┌─────────────────────┐
                  │  Training Pipeline  │
                  │   (M7: QLoRA on     │
                  │  Yamaç-only loss)   │
                  └──────────┬──────────┘
                             │ produces
                             ▼
                  ┌─────────────────────┐
                  │   Reflex Adapter    │
                  │  (yamac-adapter-vN) │
                  │    "the identity"   │
                  └──────────┬──────────┘
                             │ loaded by
                             ▼
                  ┌─────────────────────┐
                  │      Speaker        │
                  │   (Gemma 4 base +   │
                  │      adapter)       │
                  └──────────┬──────────┘
                             │ becomes
                             ▼
                  ┌─────────────────────┐
                  │     Yamaç Jr.       │
                  │  "the second-self"  │
                  └─────────────────────┘
```

### 28.J Critical Reference Repos (Read at PRD Drafting)

| Pillar | Repo | What we study |
|---|---|---|
| Reflex | mindverse/Second-Me | Behavioral cloning via session distillation |
| Reflex | letta-ai/letta | Hierarchical memory + identity persistence |
| Reflex | QuixiAI/Hexis | Persona shaping for LLM agents |
| Body | minitap-ai/mobile-use | Mobile UI control via vision |
| Body | browser-use/browser-use | Browser automation via vision + DOM |
| Body | Skyvern-AI/skyvern | Workflow-grade browser automation |
| Mind | mem0ai/mem0 | Hierarchical memory |
| Mind | topoteretes/cognee | Local-first GraphRAG |
| Mind | faugustdev/git-context-controller | Code context controller |
| Building Block | felixrieseberg/clippy | Electron + llama.cpp + GGUF reference |

---

## 29. Glossary

| Term | Definition |
|---|---|
| **ARGE** | Turkish: research & development. Refers to `docs/archive/Yamac_Jr_ARGE.pdf`. |
| **Speaker** | The primary LLM. v1: Gemma 4 E2B-it Q4_0. |
| **Watcher** | Secondary classifier model proposed in ARGE §7. **Cancelled in v1, revival path in §16.** |
| **Reflex / Body / Mind / Orchestrator** | The four architectural pillars (philosophical names). |
| **CLI Surfing** | Autonomous switching between coding CLIs based on boredom / frustration / rate limits. |
| **Perfect Payload** | Done-state notification packet sent via Telegram. |
| **Slider** | Operator-set autonomy level (0–10) gating action thresholds. |
| **Threshold** | Minimum slider value required for an action to run autonomously. |
| **Patron / Yamaç Sr.** | The human operator. **Yamaç Jr.** is the system itself. |
| **Forge** | The home compute machine: 16 GB MBP for Nano, Mac Studio Ultra for Full Vision. |
| **Nano** | The v1 release tier targeting 16 GB Apple Silicon with Gemma 4 E2B-it. |
| **Full Vision** | The v2 release tier targeting Mac Studio Ultra with Gemma 4 26B A4B + vision drivers. |
| **Daemon Mesh** | Tailscale-connected daemons across operator's machines, brain at home. |
| **Three Pillars** | Reflex + Body + Mind. The architectural triad. |
| **Korpus Reflex** | Discipline of consulting `examples_crucial/` and `examples/` before architectural decisions. |
| **Kararlar.md** | The decision SSOT, `docs/Yamac_Jr_Nano_Kararlar.md`. |
| **Anti-Hallucination Framework** | The 9 protocols in `CLAUDE.md` and §21 of this PRD. |
| **Three Experts Test** | Defender / Critic / Pragmatist mental rehearsal before important decisions. |
| **Half-Duplex** | Speaker generates without listening; chat queue folds operator inject at next breakpoint. |
| **Full-Duplex** | Speaker + Watcher running interleaved, true mid-generation inject. **Deferred.** |
| **Citation Discipline** | Project-specific claims must include `[citation: path:line]`. |
| **CoT** | Chain-of-Thought, `<think>...</think>` blocks injected into training data. |
| **QLoRA** | Quantized Low-Rank Adaptation — the chosen fine-tune method. |
| **MLX** | Apple's machine learning framework for Apple Silicon. |
| **sqlite-vec / FTS5** | SQLite extensions for dense vector and sparse keyword search. |
| **Tailscale** | WireGuard-based mesh VPN. |

---

## 30. References

- `README.md` — public-facing summary
- `CLAUDE.md` / `GEMINI.md` — operating mandate for AI partners on this codebase
- `docs/Yamac_Jr_Nano_Kararlar.md` — decision SSOT
- `docs/decisions/Yamac_Jr_Nano_UI_Orchestration_Vision.md` — UI/orchestration vision SSOT
- `docs/archive/Yamac_Jr_ARGE.pdf` — foundational research document (16 pages)
- `docs/archive/Yamac_Jr_Donanim_Arastirmasi.pdf` — hardware market analysis (3 pages)
- `docs/ROADMAP.md` — phased delivery plan
- `examples_crucial/` — 29 first-tier reference repos
- `examples/` — 60 second-tier reference repos and 11 awesome lists
- `.opencode/agents/{explorer-god,audit-god,selffork-researcher}.md` — agent ecosystem
- `apps/web/src/App.tsx` — cockpit prototype with full mock state model

---

## 31. PRD Versioning

- **1.0.0** — 2026-04-27 — initial draft after Watcher-cancellation, hybrid-pillar, CLI-Surfing-v1-core, Cockpit-full-control-v1, M0–M7 capability roadmap with fine-tune deferred to M7.

Future revisions follow semver:
- **MAJOR** bump on changes that alter the manifesto or the pillar structure.
- **MINOR** bump on milestone scope changes or new sections.
- **PATCH** bump on clarifications, glossary additions, or fixes that don't change scope.

A PRD revision must include:
- A changelog entry at the top of this section.
- A PR linked to the decision(s) that motivated the change.
- An updated `docs/Yamac_Jr_Nano_Kararlar.md` if the change reflects a new locked decision.

---

**End of PRD.**

*Tam olsun, bizim olsun. Kolaya kaçmadık.*
*Yamaç Jr. doğmak için sabırla bekliyor.*
