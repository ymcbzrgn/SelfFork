"""Generic YAML-backed Pydantic settings store with atomic write (S4).

Pattern lifted from
:class:`selffork_orchestrator.heartbeat.autonomy.AutonomyStore` —
generic so the three S4 stores (model endpoint, destructive
whitelist resolver, CodexBar user config) share atomic-write +
read-default plumbing without copy-paste. A crash mid-write leaves
the on-disk YAML untouched because the temp file replace is the
only mutating syscall.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class YamlSettingsStore[T: BaseModel]:
    """YAML-backed Pydantic store with atomic write.

    ``read`` returns ``None`` when the file is absent or unparseable;
    ``read_or_default`` substitutes a fresh ``default_factory()``
    instance instead. ``write`` persists via a sibling temp file +
    :meth:`Path.replace` so a crash mid-write never leaves the
    operator with a corrupt YAML.
    """

    path: Path
    schema: type[T]
    default_factory: Callable[[], T]

    def read(self) -> T | None:
        """Return the persisted value, or ``None`` when absent / unparseable."""
        if not self.path.is_file():
            return None
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                return None
            return self.schema.model_validate(data)
        except (OSError, yaml.YAMLError, ValidationError, ValueError) as exc:
            _log.warning(
                "yaml_settings_read_failed",
                extra={"path": str(self.path), "error": str(exc)},
            )
            return None

    def read_or_default(self) -> T:
        """Return persisted value or a fresh default instance."""
        persisted = self.read()
        if persisted is not None:
            return persisted
        return self.default_factory()

    def write(self, value: T) -> None:
        """Atomically persist ``value`` to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body: dict[str, Any] = value.model_dump(mode="json")
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            yaml.safe_dump(body, sort_keys=True, allow_unicode=True),
            encoding="utf-8",
        )
        temp.replace(self.path)

    def write_raw(self, data: dict[str, Any]) -> None:
        """Persist a pre-validated raw dict.

        Used by endpoints that accept arbitrary operator-edited YAML
        (e.g. the destructive whitelist full editor) where the
        round-trip shape doesn't perfectly fit one strict Pydantic
        schema. The caller is responsible for validation BEFORE
        invoking this method; otherwise garbage lands on disk.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        temp.replace(self.path)

    def delete(self) -> bool:
        """Remove the persisted file. Returns ``True`` if it existed."""
        if self.path.is_file():
            self.path.unlink()
            return True
        return False
