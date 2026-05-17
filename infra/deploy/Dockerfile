# syntax=docker/dockerfile:1.7
#
# SelfFork v3 — single-node self-host container.
#
# ADR-006 §4 deployment: SelfFork core (FastAPI orchestrator + Next.js
# cockpit) plus the CLI fleet (claude-code, codex, gemini-cli, etc.)
# run side-by-side in one container. The model lives external — config
# the endpoint URL in Settings → Model Endpoint.
#
# The container ships:
#   - Python 3.12 + uv for the orchestrator
#   - Node 20 LTS for the Next.js cockpit + CLI installs
#   - Playwright with chromium for headless browser-driven auth
#   - xvfb for the rare CLI that insists on an X display
#   - tmux for session lifecycle (legacy snapper bridge)
#
# Operator runs this on any Linux server (GPU not required — model
# endpoint is external). CPU-first deploy is fully supported.

FROM ubuntu:24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_VERSION=20 \
    SELFFORK_HOME=/opt/selffork

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
        python3.12 \
        python3.12-venv \
        python3-pip \
        tmux \
        xvfb \
        xauth \
        libnss3 \
        libatk1.0-0t64 \
        libatk-bridge2.0-0t64 \
        libcups2t64 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libasound2t64 \
        fonts-noto-color-emoji \
        ssh \
    && rm -rf /var/lib/apt/lists/*

# Node 20 LTS (NodeSource)
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# uv (fast Python package manager) — replaces pip/pipx for orchestrator
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# pnpm for the Next.js cockpit
RUN npm install -g pnpm@9

# CLI fleet installs (operator may override with their own pinned
# versions by rebuilding from this base; we ship the latest stable
# at build time)
RUN npm install -g \
    @anthropic-ai/claude-code \
    @google/gemini-cli \
    @openai/codex

# Playwright runtime + chromium
RUN npm install -g playwright \
    && playwright install --with-deps chromium

# Non-root operator user (running CLIs as root invites pain)
RUN useradd --create-home --home-dir ${SELFFORK_HOME} --shell /bin/bash --uid 1000 selffork

WORKDIR ${SELFFORK_HOME}

# ── App build ────────────────────────────────────────────────────────────────
FROM base AS app

# Copy monorepo into the container (Docker build context = repo root)
COPY --chown=selffork:selffork pyproject.toml uv.lock README.md LICENSE ./
COPY --chown=selffork:selffork packages/ ./packages/
COPY --chown=selffork:selffork apps/ ./apps/
COPY --chown=selffork:selffork docs/ ./docs/
COPY --chown=selffork:selffork infra/ ./infra/

USER selffork

# Python deps via uv (orchestrator + body + reflex + telegram packages)
RUN uv venv .venv \
    && . .venv/bin/activate \
    && uv pip install -e packages/orchestrator -e packages/body -e packages/reflex \
    && deactivate

# Next.js cockpit build (apps/web static export → orchestrator serves it)
RUN cd apps/web \
    && pnpm install --frozen-lockfile=false \
    && pnpm build

# Persistent state mount points (auth cookies, audit logs, mind RAG)
RUN mkdir -p \
    ${SELFFORK_HOME}/.config/selffork/auth \
    ${SELFFORK_HOME}/.selffork/projects \
    ${SELFFORK_HOME}/.selffork/audit \
    ${SELFFORK_HOME}/.selffork/mind

VOLUME ${SELFFORK_HOME}/.config/selffork
VOLUME ${SELFFORK_HOME}/.selffork

ENV PATH=${SELFFORK_HOME}/.venv/bin:${PATH} \
    SELFFORK_CONFIG_PATH=${SELFFORK_HOME}/.selffork/config.yaml \
    SELFFORK_AUDIT_DIR=${SELFFORK_HOME}/.selffork/audit \
    SELFFORK_PROJECTS_ROOT=${SELFFORK_HOME}/.selffork/projects

EXPOSE 8765

# Healthcheck hits /api/health (returns 200 once orchestrator is up)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8765/api/health || exit 1

# Entry: orchestrator FastAPI + serves the Next.js static export.
# Operator opens http://<server>:8765/ in their browser.
ENTRYPOINT ["selffork"]
CMD ["ui", "--host", "0.0.0.0", "--port", "8765", "--no-open"]
