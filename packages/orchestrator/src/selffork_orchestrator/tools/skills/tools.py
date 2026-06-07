"""Skills tools — SkillInstaller-backed operator-level skill ops (10 tools)."""

from __future__ import annotations

import asyncio
import shutil
import tarfile
from pathlib import Path
from typing import Any

from pydantic import Field

from selffork_orchestrator.skills import (
    SkillInstaller,
    default_canonical_skills_dir,
    default_target_cli_dirs,
)
from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.github._internal import _invoke_callable

__all__ = [
    "SkillCreateArgs",
    "SkillExportArgs",
    "SkillInstallArgs",
    "SkillListArgs",
    "SkillSearchArgs",
    "SkillShowArgs",
    "SkillSyncArgs",
    "SkillUninstallArgs",
    "SkillUpdateArgs",
    "SkillValidateArgs",
    "build_skills_tools_inner",
]


# ---- Args ----------------------------------------------------------------


class SkillListArgs(ToolArgs):
    canonical_dir: str | None = Field(default=None, max_length=4096)


class SkillShowArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=128)
    canonical_dir: str | None = Field(default=None, max_length=4096)


class SkillSyncArgs(ToolArgs):
    canonical_dir: str | None = Field(default=None, max_length=4096)
    target_dirs: list[str] | None = Field(
        default=None,
        description="Override fan-out targets; default = four CLI skills dirs",
    )


class SkillInstallArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=4096, description="git URL or local path")
    canonical_dir: str | None = Field(default=None, max_length=4096)


class SkillUninstallArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=128)
    canonical_dir: str | None = Field(default=None, max_length=4096)


class SkillUpdateArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=128)
    canonical_dir: str | None = Field(default=None, max_length=4096)


class SkillSearchArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=512)
    canonical_dir: str | None = Field(default=None, max_length=4096)


class SkillValidateArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=128)
    canonical_dir: str | None = Field(default=None, max_length=4096)


class SkillExportArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=128)
    output_path: str = Field(min_length=1, max_length=4096)
    canonical_dir: str | None = Field(default=None, max_length=4096)


class SkillCreateArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = Field(min_length=1, max_length=1024)
    canonical_dir: str | None = Field(default=None, max_length=4096)


# ---- Helpers -------------------------------------------------------------


def _resolve_canonical(canonical_dir: str | None) -> Path:
    if canonical_dir:
        return Path(canonical_dir).expanduser()
    return default_canonical_skills_dir()


def _skill_dir(name: str, canonical_dir: str | None) -> Path:
    return _resolve_canonical(canonical_dir) / name


async def _run_subprocess(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return {
        "returncode": proc.returncode,
        "stdout": stdout.decode(errors="replace")[:8192],
        "stderr": stderr.decode(errors="replace")[:4096],
    }


# ---- Handlers ------------------------------------------------------------


async def _skill_list(ctx: ToolContext, args: SkillListArgs) -> dict[str, Any]:
    canonical = _resolve_canonical(args.canonical_dir)
    installer = SkillInstaller(
        canonical_dir=canonical,
        target_dirs=default_target_cli_dirs(),
    )

    async def _run() -> dict[str, Any]:
        skills = installer.list_skills()
        return {
            "canonical_dir": str(canonical),
            "count": len(skills),
            "names": [p.name for p in skills],
        }

    return await _invoke_callable(
        ctx,
        action_type="skill.list",
        target_uri=str(canonical),
        args_summary={"canonical_dir": str(canonical)},
        coro_factory=_run,
    )


async def _skill_show(ctx: ToolContext, args: SkillShowArgs) -> dict[str, Any]:
    skill_dir = _skill_dir(args.name, args.canonical_dir)

    async def _run() -> dict[str, Any]:
        if not skill_dir.is_dir():
            return {"exists": False, "path": str(skill_dir)}
        manifest_path = skill_dir / "SKILL.md"
        manifest = (
            manifest_path.read_text(errors="replace")[:16_384] if manifest_path.is_file() else None
        )
        files = sorted(p.name for p in skill_dir.iterdir())
        return {
            "exists": True,
            "path": str(skill_dir),
            "manifest": manifest,
            "files": files[:200],
        }

    return await _invoke_callable(
        ctx,
        action_type="skill.show",
        target_uri=str(skill_dir),
        args_summary={"name": args.name},
        coro_factory=_run,
    )


async def _skill_sync(ctx: ToolContext, args: SkillSyncArgs) -> dict[str, Any]:
    canonical = _resolve_canonical(args.canonical_dir)
    if args.target_dirs is not None:
        targets = [Path(t).expanduser() for t in args.target_dirs]  # noqa: ASYNC240
    else:
        targets = default_target_cli_dirs()
    installer = SkillInstaller(
        canonical_dir=canonical,
        target_dirs=targets,
    )

    async def _run() -> dict[str, Any]:
        report = installer.sync_all()
        return {
            "installed": {k: len(v) for k, v in report.installed.items()},
            "skipped": {k: len(v) for k, v in report.skipped.items()},
            "conflicts": {
                k: [{"target": str(t), "reason": r} for t, r in v]
                for k, v in report.conflicts.items()
            },
        }

    return await _invoke_callable(
        ctx,
        action_type="skill.sync",
        target_uri=str(canonical),
        args_summary={"canonical_dir": str(canonical)},
        coro_factory=_run,
    )


async def _skill_install(ctx: ToolContext, args: SkillInstallArgs) -> dict[str, Any]:
    skill_dir = _skill_dir(args.name, args.canonical_dir)
    skill_dir.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> dict[str, Any]:
        if skill_dir.exists():
            return {"status": "already_installed", "path": str(skill_dir)}
        # git URL?
        if args.source.startswith(("http://", "https://", "git@", "ssh://")):
            result = await _run_subprocess(
                ["git", "clone", "--depth", "1", args.source, str(skill_dir)],
            )
            return {
                "status": "ok" if result["returncode"] == 0 else "error",
                "method": "git_clone",
                **result,
            }
        # Local path
        source = Path(args.source).expanduser()  # noqa: ASYNC240 — sync path build
        if not source.is_dir():
            return {"status": "error", "message": f"source not a dir: {source}"}
        shutil.copytree(source, skill_dir)
        return {"status": "ok", "method": "copytree", "path": str(skill_dir)}

    return await _invoke_callable(
        ctx,
        action_type="skill.install",
        target_uri=str(skill_dir),
        args_summary={"name": args.name, "source": args.source},
        coro_factory=_run,
    )


async def _skill_uninstall(ctx: ToolContext, args: SkillUninstallArgs) -> dict[str, Any]:
    skill_dir = _skill_dir(args.name, args.canonical_dir)

    async def _run() -> dict[str, Any]:
        if not skill_dir.exists():
            return {"status": "not_installed"}
        if skill_dir.is_symlink():
            skill_dir.unlink()
            return {"status": "ok", "unlinked": True}
        shutil.rmtree(skill_dir)
        return {"status": "ok", "removed": True}

    return await _invoke_callable(
        ctx,
        action_type="skill.uninstall",
        target_uri=str(skill_dir),
        args_summary={"name": args.name},
        coro_factory=_run,
    )


async def _skill_update(ctx: ToolContext, args: SkillUpdateArgs) -> dict[str, Any]:
    skill_dir = _skill_dir(args.name, args.canonical_dir)

    async def _run() -> dict[str, Any]:
        if not (skill_dir / ".git").is_dir():
            return {"status": "not_a_git_skill", "path": str(skill_dir)}
        result = await _run_subprocess(["git", "pull", "--ff-only"], cwd=skill_dir)
        return {
            "status": "ok" if result["returncode"] == 0 else "error",
            **result,
        }

    return await _invoke_callable(
        ctx,
        action_type="skill.update",
        target_uri=str(skill_dir),
        args_summary={"name": args.name},
        coro_factory=_run,
    )


async def _skill_search(ctx: ToolContext, args: SkillSearchArgs) -> dict[str, Any]:
    canonical = _resolve_canonical(args.canonical_dir)
    needle = args.query.lower()

    async def _run() -> dict[str, Any]:
        hits: list[dict[str, Any]] = []
        if not canonical.is_dir():
            return {"hits": [], "count": 0}
        for skill_dir in sorted(canonical.iterdir()):
            if not skill_dir.is_dir():
                continue
            manifest_path = skill_dir / "SKILL.md"
            if not manifest_path.is_file():
                continue
            content = manifest_path.read_text(errors="replace").lower()
            if needle in content or needle in skill_dir.name.lower():
                hits.append(
                    {
                        "name": skill_dir.name,
                        "match_in_name": needle in skill_dir.name.lower(),
                    }
                )
        return {"hits": hits[:200], "count": len(hits)}

    return await _invoke_callable(
        ctx,
        action_type="skill.search",
        target_uri=str(canonical),
        args_summary={"query_len": len(args.query)},
        coro_factory=_run,
    )


async def _skill_validate(ctx: ToolContext, args: SkillValidateArgs) -> dict[str, Any]:
    skill_dir = _skill_dir(args.name, args.canonical_dir)

    async def _run() -> dict[str, Any]:
        if not skill_dir.is_dir():
            return {"valid": False, "reason": "skill_dir_missing"}
        manifest_path = skill_dir / "SKILL.md"
        if not manifest_path.is_file():
            return {"valid": False, "reason": "missing_SKILL.md"}
        content = manifest_path.read_text(errors="replace")
        # Check for YAML frontmatter (matches the Claude skills convention)
        if not content.startswith("---\n"):
            return {"valid": False, "reason": "missing_yaml_frontmatter"}
        end = content.find("\n---\n", 4)
        if end == -1:
            return {"valid": False, "reason": "unterminated_frontmatter"}
        frontmatter = content[4:end]
        required = ("name", "description")
        missing = [k for k in required if f"{k}:" not in frontmatter]
        if missing:
            return {"valid": False, "reason": f"missing_keys:{','.join(missing)}"}
        return {"valid": True, "frontmatter_len": len(frontmatter)}

    return await _invoke_callable(
        ctx,
        action_type="skill.validate",
        target_uri=str(skill_dir),
        args_summary={"name": args.name},
        coro_factory=_run,
    )


async def _skill_export(ctx: ToolContext, args: SkillExportArgs) -> dict[str, Any]:
    skill_dir = _skill_dir(args.name, args.canonical_dir)
    output_path = Path(args.output_path).expanduser()  # noqa: ASYNC240 — sync path build

    async def _run() -> dict[str, Any]:
        if not skill_dir.is_dir():
            return {"status": "skill_missing", "path": str(skill_dir)}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # tarfile.open is sync; offload to thread.
        await asyncio.to_thread(_tar_directory, skill_dir, output_path)
        size = output_path.stat().st_size if output_path.is_file() else 0
        return {"status": "ok", "output_path": str(output_path), "bytes": size}

    return await _invoke_callable(
        ctx,
        action_type="skill.export",
        target_uri=str(output_path),
        args_summary={"name": args.name, "output_path": str(output_path)},
        coro_factory=_run,
    )


def _tar_directory(source: Path, output_path: Path) -> None:
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(source, arcname=source.name)


async def _skill_create(ctx: ToolContext, args: SkillCreateArgs) -> dict[str, Any]:
    skill_dir = _skill_dir(args.name, args.canonical_dir)

    async def _run() -> dict[str, Any]:
        if skill_dir.exists():
            return {"status": "already_exists", "path": str(skill_dir)}
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            f"name: {args.name}\n"
            f"description: {args.description}\n"
            "---\n\n"
            f"# {args.name}\n\n"
            f"{args.description}\n\n"
            "## Usage\n\nTODO: describe activation triggers + steps.\n",
            encoding="utf-8",
        )
        return {"status": "ok", "path": str(skill_dir)}

    return await _invoke_callable(
        ctx,
        action_type="skill.create",
        target_uri=str(skill_dir),
        args_summary={"name": args.name, "description_len": len(args.description)},
        coro_factory=_run,
    )


def build_skills_tools_inner() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="skill_list",
            description="List installed skills under the canonical dir.",
            args_model=SkillListArgs,
            handler=_skill_list,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_show",
            description="Show skill metadata (SKILL.md + file list).",
            args_model=SkillShowArgs,
            handler=_skill_show,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_sync",
            description=(
                "Fan-out canonical skills into each CLI's skills dir "
                "(claude/codex/gemini/opencode). Idempotent + conflict-aware."
            ),
            args_model=SkillSyncArgs,
            handler=_skill_sync,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_install",
            description=("Install a skill into the canonical dir from a git URL or local path."),
            args_model=SkillInstallArgs,
            handler=_skill_install,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_uninstall",
            description="Remove a skill (handles symlink + dir variants).",
            args_model=SkillUninstallArgs,
            handler=_skill_uninstall,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_update",
            description=(
                "Update a git-backed skill via `git pull --ff-only` inside the canonical dir."
            ),
            args_model=SkillUpdateArgs,
            handler=_skill_update,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_search",
            description=("Search canonical skills' SKILL.md + names for a substring."),
            args_model=SkillSearchArgs,
            handler=_skill_search,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_validate",
            description=(
                "Validate a skill manifest: SKILL.md exists with name+description YAML frontmatter."
            ),
            args_model=SkillValidateArgs,
            handler=_skill_validate,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_export",
            description="Export a skill directory to a .tar.gz bundle.",
            args_model=SkillExportArgs,
            handler=_skill_export,
            defer_loading=True,
        ),
        ToolSpec(
            name="skill_create",
            description=("Scaffold a new skill directory with a SKILL.md template."),
            args_model=SkillCreateArgs,
            handler=_skill_create,
            defer_loading=True,
        ),
    ]
