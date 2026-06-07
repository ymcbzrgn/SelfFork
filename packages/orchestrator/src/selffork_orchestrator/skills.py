"""SelfFork Skill installer — symlink fan-out (ADR-010 §SHOULD, S-Vision Faz F).

Hivemind H4 pattern lift ([[hivemind-adoption]]): a single canonical
``~/.selffork/skills/`` directory is the source of truth for shared
skills; each immediate skill subdir is symlinked into the user's per-CLI
skills directory (e.g. ``~/.claude/skills/<skill>``). Updates flow
through ``git pull`` on the canonical dir + a re-run of
:meth:`SkillInstaller.sync_all`.

**No marketplace server** (explicit reject in ADR-010 §SHOULD) — the
canonical dir is whatever git repo the operator clones into it.

Idempotent + conflict-aware:

* Symlink already pointing at the canonical skill → skipped (no-op).
* Symlink pointing elsewhere → reported as conflict, NOT overwritten.
* Plain file/dir at target → reported as conflict, NOT overwritten.
* Missing target dir → created on demand.

The four default targets cover the wired CLI agents (DEFAULT_CLI_IDS:
claude-code / codex / gemini-cli / opencode); custom deployments pass
explicit ``target_dirs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "SkillInstaller",
    "SkillSyncReport",
    "default_canonical_skills_dir",
    "default_target_cli_dirs",
]


def default_canonical_skills_dir() -> Path:
    """Default canonical source: ``~/.selffork/skills/``."""
    return Path("~/.selffork/skills").expanduser()


def default_target_cli_dirs() -> list[Path]:
    """Default fan-out targets — skills dirs for the four wired CLI agents."""
    return [
        Path("~/.claude/skills").expanduser(),
        Path("~/.codex/skills").expanduser(),
        Path("~/.gemini/skills").expanduser(),
        Path("~/.opencode/skills").expanduser(),
    ]


@dataclass(slots=True)
class SkillSyncReport:
    """Outcome of one :meth:`SkillInstaller.sync_all` run.

    Mutable on purpose — the installer mutates the dicts as it iterates;
    callers treat the report as read-only after the call returns.

    Attributes:
        installed: skill name → list of ``(target_root, created_link)``
            for new symlinks created on this run.
        skipped: skill name → list of ``target_root``s where the correct
            symlink already existed (no-op).
        conflicts: skill name → list of ``(target_root, reason)`` where
            something blocked the link (existing symlink to a different
            source, a plain file, a plain dir, etc.).
    """

    installed: dict[str, list[tuple[Path, Path]]] = field(default_factory=dict)
    skipped: dict[str, list[Path]] = field(default_factory=dict)
    conflicts: dict[str, list[tuple[Path, str]]] = field(default_factory=dict)


class SkillInstaller:
    """Fan-out installer — symlink each canonical skill into every target dir.

    Construct once with a canonical source + a target list; call
    :meth:`sync_all` repeatedly (idempotent). Conflicts are reported, not
    forced — the operator inspects the report and resolves manually.
    """

    def __init__(
        self,
        *,
        canonical_dir: Path,
        target_dirs: list[Path],
    ) -> None:
        self._canonical = canonical_dir
        self._targets = list(target_dirs)

    @property
    def canonical_dir(self) -> Path:
        return self._canonical

    @property
    def target_dirs(self) -> list[Path]:
        return list(self._targets)

    def list_skills(self) -> list[Path]:
        """Return every immediate subdir of the canonical source, sorted.

        Empty list when the canonical dir is missing — the installer is a
        no-op rather than a failure (boot ordering: the dashboard may run
        ``sync_all`` before the operator has populated the canonical dir).
        """
        if not self._canonical.is_dir():
            return []
        return sorted(p for p in self._canonical.iterdir() if p.is_dir())

    def sync_all(self) -> SkillSyncReport:
        """Symlink every canonical skill into every target dir."""
        report = SkillSyncReport()
        for skill_dir in self.list_skills():
            skill_name = skill_dir.name
            for target_root in self._targets:
                target_root.mkdir(parents=True, exist_ok=True)
                target_link = target_root / skill_name
                outcome = self._link_one(skill_dir, target_link)
                if outcome == "installed":
                    report.installed.setdefault(skill_name, []).append((target_root, target_link))
                elif outcome == "skipped":
                    report.skipped.setdefault(skill_name, []).append(target_root)
                else:
                    report.conflicts.setdefault(skill_name, []).append((target_root, outcome))
        return report

    def _link_one(self, source: Path, target_link: Path) -> str:
        """Create ``target_link → source``; return an outcome string.

        Outcome vocabulary:

        * ``"installed"`` — link created.
        * ``"skipped"`` — link already pointed at the canonical source.
        * ``"symlink_to_other: <resolved>"`` — link existed but pointed
          elsewhere.
        * ``"target_is_dir"`` / ``"target_is_file"`` — a non-symlink
          blocked the target path.
        * ``"target_unresolvable: <error>"`` — broken symlink we cannot
          inspect.
        """
        if target_link.is_symlink():
            try:
                resolved = target_link.resolve(strict=False)
            except OSError as exc:
                return f"target_unresolvable: {exc}"
            if resolved == source.resolve():
                return "skipped"
            return f"symlink_to_other: {resolved}"
        if target_link.exists():
            kind = "dir" if target_link.is_dir() else "file"
            return f"target_is_{kind}"
        target_link.symlink_to(source, target_is_directory=True)
        return "installed"

    @classmethod
    def default(cls) -> SkillInstaller:
        """Construct against the default canonical + four-CLI target dirs."""
        return cls(
            canonical_dir=default_canonical_skills_dir(),
            target_dirs=default_target_cli_dirs(),
        )
