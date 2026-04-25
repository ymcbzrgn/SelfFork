# SelfFork (Yamaç Jr. Nano)

> **Autonomous Executive Mission Control & CLI Orchestrator**

SelfFork is a high-performance, autonomous system designed for the "Patron" (Executive) who demands full project automation with surgical precision. It operates as a singular, fine-tuned orchestrator (Yamaç Jr.) that lives on a GPU server, choreographs multiple CLI tools, manages subscription-based rate limits via autonomous scheduling, and deploys verified payloads directly to production CPU servers via SSH.

---

## 🚀 The Vision: Executive Autonomy

SelfFork is not a chat bot; it is an **Autonomous Operating System** for software engineering. It reflects the developer's own habits—getting frustrated with failing models, surfing through different CLI tools (`gemini-cli`, `opencode`, `claude code`), and managing "Free-Tier" subscription quotas without human intervention.

### Core Architectural Pillars

*   **Executive Mission Control:** A hierarchical, light-themed web dashboard for high-level fleet management and deep-dive workspace intervention.
*   **CLI Surfing (Tmux Swarm):** Dynamically switches between AI models and CLI tools based on boredom, frustration, or rate limits. If Gemini hits a 429, the agent kills the tmux pane and surfs to Minimax or GLM.
*   **Autonomous Scheduler (Cron/Sleep):** When all subscription quotas are exhausted, the agent autonomously schedules a Linux `cron` job, notifies the Patron via Telegram, and goes to sleep until reset.
*   **Shadow CI/CD Validation:** All development occurs in isolated containers on the GPU "Forge" server. Code is never pushed to PROD without passing rigorous shadow tests.
*   **Zero-Footprint Deployment:** Pure SSH-based delivery to CPU servers. No development daemons or heavy dependencies are left on the production environment.

---

## 🛠 Project Structure

```text
SelfFork/
├── apps/
│   └── web/                # React + Vite: Executive Mission Control Dashboard
├── packages/
│   ├── orchestrator/       # The Brain: Tmux management & CLI Surfing logic
│   ├── body/               # The Limbs: SSH Drivers & Remote Execution
│   └── mind/               # The Memory: Isolated RAG & Knowledge Base
├── docs/
│   └── decisions/          # Single Source of Truth (SSOT) documents
└── README.md
```

---

## 🖥 The Dashboard Experience

The UI is designed to be **simple yet powerful**, following an "Executive Hierarchy":

1.  **Login:** Clean, bright authentication entry point.
2.  **Fleet Command Center:** A bird's-eye view of all active projects with color-coded statuses (Sleeping, CLI Surfing, Deployed) and global subscription quota monitors.
3.  **Isolated Workspace:** A dedicated deep-dive environment for each project featuring:
    *   **Operations Board:** Autonomous Kanban for task tracking.
    *   **Live Tmux Telemetry:** Real-time monitoring of the active CLI engines.
    *   **Direct Line Chat:** Immediate, web-based communication with the Yamaç Jr. agent.
    *   **Studio (IDE & Git):** A Firebase-style control panel for manual code intervention and source control.
    *   **Knowledge Base:** Persistent RAG context and architectural decision logs.

---

## ⚙️ Technology Stack

*   **Frontend:** React 19, TypeScript, Vite, Vanilla CSS (Enterprise Quality).
*   **Backend:** Node.js / Python (Orchestrator core).
*   **Runtime:** Tmux (Multi-pane CLI Swarm), Docker (Shadow Environment).
*   **AI Engines:** Yamaç Jr. Fine-Tuned Adapter (Gemma 4 base).
*   **CLI Tools:** Gemini CLI, Claude Code, OpenCode (Minimax, GLM).

---

## 📜 License

Apache License 2.0. See [LICENSE](LICENSE) for details.

---

**"Tam olsun, bizim olsun."** — *Quality before speed, autonomy before assistance.*
