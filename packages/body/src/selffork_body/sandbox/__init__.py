"""Body action-level sandbox — placeholder until M5.

Per-tool-call permission warden, action audit, kill switch. **Distinct
from the orchestrator-level sandbox** (env isolation) at
``selffork_orchestrator.sandbox`` — no shared interface; different layer.
"""

from __future__ import annotations
