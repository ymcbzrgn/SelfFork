# selffork-shared

Cross-pillar primitives. Imported by every pillar; imports nothing from any pillar.

See [ADR-001 §4](../../docs/decisions/ADR-001_MVP_v0.md) for the boundary discipline.

## Modules (planned for MVP v0)

| Module | Purpose | Reference |
|---|---|---|
| `config` | Pydantic v2 settings + `selffork.yaml` loader + env override | ADR-001 §7 |
| `logging` | `structlog` JSON setup + correlation IDs | ADR-001 §8 |
| `errors` | `SelfForkError` typed hierarchy | ADR-001 §9 |
| `audit` | jsonl audit logger + redaction | ADR-001 §10 |
| `ports` | Free-port allocation (`headroom/cli/wrap.py:101-109` port-probe pattern) | ADR-001 §13 |
| `ulid` | Correlation/session ID generation | — |
| `shellquote` | zsh-safe shell quoting (`amux:171-194` pattern) | ADR-001 §13 |

Implementation lands in **step 2** per ADR-001 §17.
