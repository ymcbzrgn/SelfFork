# SelfFork — opencode-runtime base image.
#
# Used by ``DockerSandbox`` (server-side multi-project mode). Contains:
#   - Python 3.12 (for any in-container Python tooling)
#   - Node.js 20 (opencode is a TS/Node CLI)
#   - opencode CLI (installed globally)
#   - git, curl, ca-certificates (basic toolchain)
#
# We stay on a slim base; the LLM runtime (mlx-server / ollama / llama.cpp /
# vllm) is HOST-side, not in the container — opencode talks to it over
# the network via the env-injected ``OPENAI_BASE_URL``.
#
# See: docs/decisions/ADR-001_MVP_v0.md §5.2, §13.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# System toolchain.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
 && rm -rf /var/lib/apt/lists/*

# Node.js 20 (for opencode CLI).
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get update \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# opencode CLI — the package name will likely change before v1; pin in CI
# once the upstream registry settles. For MVP we install the placeholder.
RUN npm install -g opencode-ai || \
    echo "WARN: opencode-ai install skipped — placeholder package name. \
Fix in step 11 when wiring real e2e tests."

# uv for any in-container Python work.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /workspace

# DockerSandbox runs ``sleep infinity`` and drives work via ``docker exec``.
CMD ["sleep", "infinity"]
