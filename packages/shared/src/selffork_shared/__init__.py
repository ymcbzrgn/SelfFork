"""SelfFork shared primitives.

Cross-pillar config, logging, errors, audit, ports, ulid, shellquote.
Imported by every pillar; imports nothing from any pillar.

See: ``docs/decisions/ADR-001_MVP_v0.md`` §4 (boundary discipline).
"""

from __future__ import annotations

__version__ = "0.0.1"
