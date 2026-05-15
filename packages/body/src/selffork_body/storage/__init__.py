"""Body pillar persistence layer (M5 — ADR-005 §M5-D3).

Currently exports :class:`ScreenshotStore` for vision pipeline frame persistence.
Path policy: ``~/.selffork/projects/<slug>/screenshots/<session_id>/<ts>_<sha8>.png``;
orphan sessions land at ``~/.selffork/screenshots/orphan/<session_id>/...``.

Audit JSONL never carries inline image bytes (see
``selffork_orchestrator.lifecycle.session._redact_image_payload``); only path
references stamped on ``body.observation`` events.
"""

from __future__ import annotations

from selffork_body.storage.screenshots import ScreenshotRef, ScreenshotStore

__all__ = ["ScreenshotRef", "ScreenshotStore"]
