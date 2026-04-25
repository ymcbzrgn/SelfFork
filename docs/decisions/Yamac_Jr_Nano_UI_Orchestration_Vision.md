# Single Source of Truth: Yamaç Jr. Nano — The True Vision

**Core Mandate:**
The system is driven by a singular, fine-tuned model (Yamaç Jr.) acting as the Orchestrator. It does NOT use a "swarm" of different personas. It acts exactly like the user (Yamaç): it gets bored, it gets frustrated, it cycles through multiple CLI tools (`gemini-cli`, `opencode`, `claude code`), and it strictly surfs $10-$20 free/cheap tier API limits. It works on a GPU server, and when finished, SSHes directly into a CPU server (PROD) to deploy. 

**Justification:**
The user's vision is pure automation reflecting their own habits. If a model fails or hits a rate limit, the Orchestrator kills the tmux pane and switches to another tool (e.g., `opencode --model minimax`). If all quotas are exhausted, it autonomously schedules a cron job to wake up in 3 hours, sends a Telegram message ("Limitler bitti, 3 saat sonra devam"), and goes to sleep.

---

## 1. The Architectural Pillars

### A. The PRD & Personal Data Ingestion
- **Concept:** The user creates a project, pastes the PRD (Product Requirements Document), and provides instructions for pulling personal data/context.
- **Execution:** The agent reads these instructions, fetches the necessary context, and autonomously generates a Kanban backlog.

### B. Single-Agent Multi-CLI Orchestration (Tmux)
- **Concept:** The agent lives on the GPU server. It opens `tmux` sessions and spawns CLI tools. 
- **The "Boredom/Frustration" Surf:** If `gemini-cli` fails to resolve an issue after a few tries, or if the agent simply gets "bored/unsatisfied" with the output, it kills the pane. It then opens `opencode --model glm` or `claude code` to try a different approach.
- **Cost Efficiency:** It leverages the user's cheap 10$-20$ auth packages across various models (Minimax, GPT-4o-mini, GLM, Gemini Pro).

### C. The Autonomous Scheduler (Cron & Sleep)
- **Concept:** The agent tracks rate limits (429 errors).
- **Execution:** When it hits a hard limit on its primary tools, it does NOT wait idly. It schedules a Linux `cron` job (e.g., `sleep 3h && resume_orchestrator`), sends a quick Telegram update to the Patron, and shuts down its active loop to save resources.

### D. Zero-Touch CPU Deployment (PROD)
- **Concept:** Development and Shadow CI/CD happen on the GPU server. The CPU servers are purely for production.
- **Execution:** Once the feature is complete and verified, the agent uses its injected SSH keys to connect to the CPU server, clone/pull the code, stand up the environment, and take a screenshot/video.

### E. Telegram "Perfect Payload" Asynchrony
- **Concept:** The agent only messages the user for two reasons: (1) Limits are exhausted and it is going to sleep, or (2) The job is done.
- **Execution:** Upon deployment, it sends a "Perfect Payload" to Telegram containing a 15-second video/screenshot of the working app on the CPU server, and waits for feedback or revision requests.

---

## 2. The Simple, Hierarchical UI

1. **Login:** A clean, bright authentication screen.
2. **Fleet Command (Projects):** Color-coded cards showing the status of all active projects (e.g., Sleeping, CLI Surfing, Deployed).
3. **Workspace (Project Details):** Deep-dive tabs that perfectly map to the vision:
   - **PRD & Instructions:** Initial prompt and personal data context.
   - **Operations Board:** The fixed, working Kanban board where the agent moves tickets.
   - **CLI Orchestration (Tmux):** Watching the agent kill `gemini-cli` and start `opencode` in real-time.
   - **Scheduler & Limits:** Countdown timers for API quotas and scheduled wake-ups.
   - **Payloads & Telegram Logs:** A history of what was sent to the user.
   - **Auth & SSH Vault:** Where the cheap-tier API keys and CPU server SSH keys reside.
