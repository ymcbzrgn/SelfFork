# opencode-runtime image

Base image for SelfFork's `DockerSandbox` mode. Built once per release;
each session-container is a `--rm` instance of this image bind-mounted
to a host workspace dir.

## Build

```bash
docker build -t selffork/opencode-runtime:latest infra/docker/opencode-runtime/
```

## What's inside

| Layer | Contents | Why |
|---|---|---|
| `python:3.12-slim` | Python 3.12, glibc | base |
| apt | `ca-certificates`, `curl`, `git`, `gnupg` | toolchain |
| nodesource | Node.js 20 | opencode is a TS/Node CLI |
| `npm i -g opencode-ai` | opencode CLI | the agent we orchestrate |
| `uv` | Python package manager | for any in-container Python work |

The LLM runtime (mlx-server / ollama / llama.cpp / vllm) is **HOST-side**,
not in the container. opencode talks to it via the env-injected
`OPENAI_BASE_URL`.

## Pinning

The opencode npm package name (`opencode-ai`) is a placeholder. Step 11
of the MVP pins the real package + version once we have a real e2e test
to validate against.

See [`docs/decisions/ADR-001_MVP_v0.md`](../../../docs/decisions/ADR-001_MVP_v0.md) §5.2, §13.
