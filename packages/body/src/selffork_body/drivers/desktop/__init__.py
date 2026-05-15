"""Desktop driver namespace (M5 — ADR-005 §M5-C4).

Two sub-drivers:

* :mod:`selffork_body.drivers.desktop.macos` — native AX-tree primary +
  screencapture screenshot fallback + AppleScript runner. Linux + Windows
  desktop drivers land in M6.
* :mod:`selffork_body.drivers.desktop.tmux` — M3 snapper-fleet adapter
  routing CLI control through the body action surface.
"""

from __future__ import annotations
