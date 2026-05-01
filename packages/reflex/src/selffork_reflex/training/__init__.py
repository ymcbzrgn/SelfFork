"""Reflex adapter training — placeholder until M7.

Will host:
  - MLX or Unsloth training driver (decision TBD per Kararlar §13.F)
  - user-only weighted-loss masking (1.0 last / 0.3 prev / 0.0 agent+tool)
  - Adapter checkpoint writer + versioning
"""

from __future__ import annotations
