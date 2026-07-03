"""``selffork mind`` typer sub-app.

Per ADR-002 §1 + Order 2: operator-facing CLI to inspect and write Mind
notes, run recall queries, and emit compaction signals (Order 3 wires
real compaction; Order 2 ships the surface). Every command emits an
audit event so behaviour is observable in the dashboard.

Subcommands:

- ``selffork mind note add "<content>" [--tier T] [--intent X] [--project P]
  [--tag k=v ...] [--path-scope GLOB ...]``
- ``selffork mind recall "<query>" [--top-k N] [--tier T] [--project P]
  [--threshold F] [--json]``
- ``selffork mind list [--tier T] [--project P] [--limit N]``
- ``selffork mind show <id>``
- ``selffork mind supersede <id> --new-content "<text>" [--new-intent ...]``
- ``selffork mind compact [--strategy {recency|distill|cluster|llm}]
  [--tier T] [--dry-run|--apply]`` — L1/L2/L3 land in Order 3 with
  ``--apply`` live; ``--strategy llm`` is a dry-run preview only and
  delegates live LLM consolidation to ``selffork mind reflect``.
- ``selffork mind reflect`` — Anthropic Auto Dream four-phase
  reflection cycle (T5; Order 5).
- ``selffork mind stats``
- ``selffork mind export-corpus --tier procedural --out FILE.jsonl`` —
  Mind T4 Procedural → Reflex training corpus (Order 6 three-pillar
  bridge with Bjork desirable difficulties + SM-2).

The CLI loads :class:`MindConfig` from ``selffork.yaml`` (or env). Per-
project paths route to ``~/.selffork/projects/<slug>/mind/`` when a
``--project`` flag is set; otherwise to ``~/.selffork/mind/``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import typer

from selffork_mind.compaction import (
    ImportanceDistiller,
    MedoidClusterCompactor,
    RecencyDecayCompactor,
    apply_plan,
)
from selffork_mind.memory.model import Note, NoteKind, TierName
from selffork_mind.memory.tags import Tag
from selffork_mind.memory.tiers import (
    EpisodicWriter,
    ProceduralDistiller,
    Reflector,
)
from selffork_mind.projections.markdown import (
    MarkdownProjection,
    MarkdownProjectionConfig,
)
from selffork_mind.projections.provenance import ProvenanceRecorder
from selffork_mind.rag.embedder import EmbedderName, EmbeddingProvider, build_embedder
from selffork_mind.rag.retriever import HybridRetriever
from selffork_mind.store import DuckDBMindStore, RetrieveConfig, StoreScope
from selffork_shared.audit import AuditLogger
from selffork_shared.config import (
    AuditConfig,
    MindConfig,
    SelfForkSettings,
    load_settings,
)

__all__ = ["mind_app"]


mind_app = typer.Typer(
    name="mind",
    help=("Inspect and write SelfFork Mind notes, run recall queries, emit compaction signals."),
    no_args_is_help=True,
    rich_markup_mode=None,
)


_VALID_TIERS: tuple[TierName, ...] = (
    "working",
    "episodic",
    "semantic_graph",
    "procedural",
    "reflection",
    "recall",
)
_VALID_KINDS: tuple[NoteKind, ...] = (
    "decision",
    "observation",
    "pattern",
    "reflection",
    "pointer",
)


# ── Path resolution ───────────────────────────────────────────────────────


def _resolve_mind_root(
    *,
    config: MindConfig,
    project_slug: str | None,
) -> Path:
    if project_slug is not None:
        return Path("~/.selffork/projects").expanduser() / project_slug / "mind"
    return Path(config.storage_root).expanduser()


def _resolve_db_path(*, root: Path) -> Path:
    return root / "notes.duckdb"


def _resolve_audit_dir(audit: AuditConfig) -> Path:
    return Path(audit.audit_dir).expanduser()


def _audit_logger(settings: SelfForkSettings, *, session_id: str) -> AuditLogger:
    return AuditLogger(settings.audit, session_id=session_id)


# ── Settings + store helpers ──────────────────────────────────────────────


def _load_settings(config_path: Path | None) -> SelfForkSettings:
    return load_settings(config_path)


def _build_embedder(config: MindConfig) -> EmbeddingProvider | None:
    if config.embedder == "none":
        return None
    name: EmbedderName = config.embedder
    return build_embedder(name)


def _build_projection(
    config: MindConfig,
    *,
    project_slug: str | None,
) -> MarkdownProjection | None:
    """Build a markdown projection rooted under the project's mind dir.

    Per-project: ``~/.selffork/projects/<slug>/mind/markdown/``. Orphan:
    the configured ``mind.projection_root``. Returns ``None`` if the
    operator wants Mind enabled but explicitly opts out (set
    ``projection_root`` to empty string).
    """
    if not config.projection_root:
        return None
    if project_slug is not None:
        root = Path("~/.selffork/projects").expanduser() / project_slug / "mind" / "markdown"
    else:
        root = Path(config.projection_root).expanduser()
    return MarkdownProjection(MarkdownProjectionConfig(root=root))


def _build_provenance(
    config: MindConfig,
    *,
    project_slug: str | None,
) -> ProvenanceRecorder | None:
    """Per-project provenance log, or the orphan default."""
    if not config.provenance_path:
        return None
    if project_slug is not None:
        log_path = (
            Path("~/.selffork/projects").expanduser() / project_slug / "mind" / "provenance.jsonl"
        )
    else:
        log_path = Path(config.provenance_path).expanduser()
    return ProvenanceRecorder(log_path=log_path)


async def _open_store(*, root: Path) -> DuckDBMindStore:
    db = _resolve_db_path(root=root)
    db.parent.mkdir(parents=True, exist_ok=True)
    store = DuckDBMindStore(db_path=db)
    await store.setup()
    return store


def _parse_tag(value: str) -> tuple[str, str]:
    """Parse a ``--tag k=v`` flag value."""
    if "=" not in value:
        raise typer.BadParameter(
            f"--tag must be 'key=value', got {value!r}",
        )
    k, v = value.split("=", 1)
    k = k.strip()
    v = v.strip()
    if not k or not v:
        raise typer.BadParameter(f"--tag {value!r} must have non-empty key and value")
    return k, v


def _validate_tier(value: str | None) -> TierName | None:
    if value is None:
        return None
    for valid in _VALID_TIERS:
        if value == valid:
            return valid
    raise typer.BadParameter(
        f"--tier must be one of {list(_VALID_TIERS)}, got {value!r}",
    )


def _validate_kind(value: str) -> NoteKind:
    for valid in _VALID_KINDS:
        if value == valid:
            return valid
    raise typer.BadParameter(
        f"--kind must be one of {list(_VALID_KINDS)}, got {value!r}",
    )


def _audit_session_id() -> str:
    return f"mind-cli-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"


# ── note add ──────────────────────────────────────────────────────────────


@mind_app.command("note")
def note_subcmd() -> None:  # pragma: no cover — typer discovery shim
    """Note operations. See ``selffork mind note --help``."""


_note_app = typer.Typer(
    name="note",
    help="Write Mind notes (single-shot CLI).",
    no_args_is_help=True,
    rich_markup_mode=None,
)
mind_app.add_typer(_note_app, name="note")


@_note_app.command("add")
def note_add(
    content: Annotated[str, typer.Argument(..., help="Note content (the body).")],
    tier: Annotated[
        str,
        typer.Option(
            "--tier",
            help="One of working/episodic/semantic_graph/procedural/reflection/recall.",
        ),
    ] = "episodic",
    kind: Annotated[
        str,
        typer.Option("--kind", help="One of decision/observation/pattern/reflection/pointer."),
    ] = "observation",
    intent: Annotated[
        str,
        typer.Option("--intent", help="Short human-readable label (≤200 chars)."),
    ] = "",
    project: Annotated[
        str | None,
        typer.Option("--project", help="Project slug to scope this note."),
    ] = None,
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", help="Session id to attribute this note to."),
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option(
            "--tag",
            help="Repeatable; format 'key=value'.",
        ),
    ] = None,
    path_scope: Annotated[
        list[str] | None,
        typer.Option(
            "--path-scope",
            help="Repeatable; glob pattern(s) — note only injected when matching files are open.",
        ),
    ] = None,
    importance: Annotated[
        float,
        typer.Option("--importance", min=0.0, max=10.0, help="Recency-decay scoring input."),
    ] = 1.0,
    pinned: Annotated[
        bool,
        typer.Option("--pinned/--no-pinned", help="Override decay; never evicted by compaction."),
    ] = False,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Path to selffork.yaml."),
    ] = None,
) -> None:
    """Write a single note to Mind."""
    settings = _load_settings(config_path)
    if not settings.mind.enabled:
        typer.echo("selffork mind: Mind is disabled in config (mind.enabled=false).", err=True)
        raise typer.Exit(code=2)
    tier_name = _validate_tier(tier)
    kind_name = _validate_kind(kind)
    if tier_name is None:
        raise typer.BadParameter("--tier is required")
    tag_pairs = [_parse_tag(t) for t in (tag or [])]
    asyncio.run(
        _note_add_async(
            settings=settings,
            content=content,
            tier=tier_name,
            kind=kind_name,
            intent=intent,
            project_slug=project,
            session_id=session_id,
            tag_pairs=tag_pairs,
            path_scope=tuple(path_scope or ()),
            importance=importance,
            pinned=pinned,
        ),
    )


async def _note_add_async(
    *,
    settings: SelfForkSettings,
    content: str,
    tier: TierName,
    kind: NoteKind,
    intent: str,
    project_slug: str | None,
    session_id: str | None,
    tag_pairs: list[tuple[str, str]],
    path_scope: tuple[str, ...],
    importance: float,
    pinned: bool,
) -> None:
    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    store = await _open_store(root=root)
    audit = _audit_logger(settings, session_id=_audit_session_id())
    try:
        note = Note(
            tier=tier,
            kind=kind,
            content=content,
            intent=intent,
            project_slug=project_slug,
            session_id=session_id,
            path_scope=path_scope,
            importance=importance,
            pinned=pinned,
        )
        stored = await store.upsert_note(note)
        if tag_pairs:
            await store.attach_tags(
                [Tag.now(note_id=stored.id, key=k, value=v) for k, v in tag_pairs],
            )
        embedder = _build_embedder(settings.mind)
        if embedder is not None:
            vector = (await embedder.embed([content]))[0]
            await store.attach_embedding(
                note_id=stored.id,
                vector=vector,
                embedder_name=embedder.name,
            )
        audit.emit(
            "mind.note.write",
            payload={
                "note_id": str(stored.id),
                "tier": stored.tier,
                "kind": stored.kind,
                "project_slug": stored.project_slug,
                "tag_count": len(tag_pairs),
                "embedder": embedder.name if embedder is not None else None,
            },
        )
        # Plain-md projection refresh (Anthropic / Cursor 2.1 lesson, ADR-002 §7)
        projection = _build_projection(settings.mind, project_slug=project_slug)
        if projection is not None:
            try:
                hits = await store.retrieve(
                    RetrieveConfig(
                        scope=StoreScope(project_slug=project_slug),
                        top_k=500,
                        rerank_overfetch=1,
                    ),
                )
                projection.write([h.note for h in hits])
                audit.emit(
                    "mind.projection.write",
                    payload={
                        "root": str(projection.root),
                        "note_count": len(hits),
                    },
                )
            except OSError:
                # Projection is observability — never block note write.
                pass
        typer.echo(f"id: {stored.id}")
        typer.echo(f"tier: {stored.tier}  kind: {stored.kind}")
        typer.echo(f"intent: {stored.intent or '(none)'}")
    finally:
        await store.teardown()


# ── recall ────────────────────────────────────────────────────────────────


@mind_app.command("recall")
def recall_cmd(
    query: Annotated[str, typer.Argument(..., help="Recall query string.")],
    top_k: Annotated[int, typer.Option("--top-k", min=1, max=200)] = 10,
    threshold: Annotated[float, typer.Option("--threshold", min=0.0, max=1.0)] = 0.0,
    tier: Annotated[
        str | None,
        typer.Option("--tier", help="Restrict to a single tier."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Restrict to a project slug."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json/--no-json", help="Emit JSONL of hits instead of plain text."),
    ] = False,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Path to selffork.yaml."),
    ] = None,
) -> None:
    """Run a Mind recall and print the hits."""
    settings = _load_settings(config_path)
    if not settings.mind.enabled:
        typer.echo("selffork mind: Mind is disabled in config (mind.enabled=false).", err=True)
        raise typer.Exit(code=2)
    tier_name = _validate_tier(tier)
    asyncio.run(
        _recall_async(
            settings=settings,
            query=query,
            top_k=top_k,
            threshold=threshold,
            tier=tier_name,
            project_slug=project,
            json_output=json_output,
        ),
    )


async def _recall_async(
    *,
    settings: SelfForkSettings,
    query: str,
    top_k: int,
    threshold: float,
    tier: TierName | None,
    project_slug: str | None,
    json_output: bool,
) -> None:
    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    store = await _open_store(root=root)
    audit = _audit_logger(settings, session_id=_audit_session_id())
    try:
        embedder = _build_embedder(settings.mind)
        provenance = _build_provenance(settings.mind, project_slug=project_slug)
        retriever = HybridRetriever(
            store=store,
            embedder=embedder,
            provenance=provenance,
        )
        tiers: tuple[TierName, ...] = (tier,) if tier is not None else ()
        hits = await retriever.recall(
            query=query,
            scope=StoreScope(project_slug=project_slug),
            tiers=tiers,
            top_k=top_k,
            threshold=threshold,
        )
        audit.emit(
            "mind.recall.query",
            payload={
                "query": query,
                "tier": tier,
                "project_slug": project_slug,
                "top_k": top_k,
                "threshold": threshold,
                "hit_count": len(hits),
            },
        )
        if json_output:
            for h in hits:
                typer.echo(
                    json.dumps(
                        {
                            "id": str(h.note.id),
                            "tier": h.note.tier,
                            "kind": h.note.kind,
                            "score": h.score,
                            "intent": h.note.intent,
                            "content": h.note.content,
                            "project_slug": h.note.project_slug,
                            "session_id": h.note.session_id,
                        },
                        ensure_ascii=False,
                    ),
                )
            return
        if not hits:
            typer.echo("selffork mind: no hits.")
            return
        typer.echo(f"selffork mind: {len(hits)} hit(s) for {query!r}")
        for h in hits:
            label = h.note.intent or h.note.content.splitlines()[0][:80]
            typer.echo(
                f"  [{h.note.tier}/{h.note.kind} score={h.score:.3f}]  {label}  ({h.note.id})",
            )
    finally:
        await store.teardown()


# ── list ──────────────────────────────────────────────────────────────────


@mind_app.command("list")
def list_cmd(
    tier: Annotated[
        str | None,
        typer.Option("--tier", help="Restrict to a single tier."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Restrict to a project slug."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 20,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Path to selffork.yaml."),
    ] = None,
) -> None:
    """List notes ordered by recency / pinned / importance."""
    settings = _load_settings(config_path)
    if not settings.mind.enabled:
        typer.echo("selffork mind: Mind is disabled.", err=True)
        raise typer.Exit(code=2)
    tier_name = _validate_tier(tier)
    asyncio.run(
        _list_async(
            settings=settings,
            tier=tier_name,
            project_slug=project,
            limit=limit,
        ),
    )


async def _list_async(
    *,
    settings: SelfForkSettings,
    tier: TierName | None,
    project_slug: str | None,
    limit: int,
) -> None:
    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    store = await _open_store(root=root)
    try:
        config = RetrieveConfig(
            tiers=(tier,) if tier is not None else (),
            scope=StoreScope(project_slug=project_slug),
            top_k=limit,
            rerank_overfetch=1,
        )
        hits = await store.retrieve(config)
        if not hits:
            typer.echo("selffork mind: no notes.")
            return
        for h in hits[:limit]:
            label = h.note.intent or h.note.content.splitlines()[0][:80]
            pinned = " [pinned]" if h.note.pinned else ""
            typer.echo(
                f"  [{h.note.tier:<14} {h.note.kind:<11}]{pinned}  {label}  ({h.note.id})",
            )
    finally:
        await store.teardown()


# ── show ──────────────────────────────────────────────────────────────────


@mind_app.command("show")
def show_cmd(
    note_id: Annotated[str, typer.Argument(..., help="UUID of the note to print.")],
    project: Annotated[
        str | None,
        typer.Option("--project"),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Path to selffork.yaml."),
    ] = None,
) -> None:
    """Print a single note + its tags."""
    try:
        nid = UUID(note_id)
    except ValueError as exc:
        typer.echo(f"selffork mind: invalid note id {note_id!r}", err=True)
        raise typer.Exit(code=2) from exc
    settings = _load_settings(config_path)
    if not settings.mind.enabled:
        typer.echo("selffork mind: Mind is disabled.", err=True)
        raise typer.Exit(code=2)
    asyncio.run(_show_async(settings=settings, note_id=nid, project_slug=project))


async def _show_async(
    *,
    settings: SelfForkSettings,
    note_id: UUID,
    project_slug: str | None,
) -> None:
    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    store = await _open_store(root=root)
    try:
        note = await store.get_note(note_id)
        if note is None:
            typer.echo(f"selffork mind: note {note_id} not found.", err=True)
            raise typer.Exit(code=2)
        tags = await store.list_tags(note_id)
        typer.echo(f"id:           {note.id}")
        typer.echo(f"tier:         {note.tier}")
        typer.echo(f"kind:         {note.kind}")
        typer.echo(f"intent:       {note.intent or '(none)'}")
        typer.echo(f"project_slug: {note.project_slug or '(none)'}")
        typer.echo(f"session_id:   {note.session_id or '(none)'}")
        typer.echo(f"valid_from:   {note.valid_from.isoformat()}")
        valid_until_str = (
            note.valid_until.isoformat() if note.valid_until is not None else "(currently valid)"
        )
        typer.echo(f"valid_until:  {valid_until_str}")
        typer.echo(f"path_scope:   {list(note.path_scope) or '(unscoped)'}")
        typer.echo(f"importance:   {note.importance}  pinned: {note.pinned}")
        if tags:
            typer.echo("tags:")
            for t in tags:
                typer.echo(f"  {t.key}={t.value}  ({t.created_at.isoformat()})")
        typer.echo("")
        typer.echo("content:")
        typer.echo(note.content)
    finally:
        await store.teardown()


# ── supersede ─────────────────────────────────────────────────────────────


@mind_app.command("supersede")
def supersede_cmd(
    note_id: Annotated[str, typer.Argument(..., help="UUID of the decision to supersede.")],
    new_content: Annotated[
        str,
        typer.Option("--new-content", help="Body of the replacement decision."),
    ],
    new_intent: Annotated[
        str | None,
        typer.Option("--new-intent", help="Optional new intent label."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project"),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config"),
    ] = None,
) -> None:
    """Mark a decision-kind note as superseded; write a new one. Bi-temporal (Graphiti)."""
    try:
        nid = UUID(note_id)
    except ValueError as exc:
        typer.echo(f"selffork mind: invalid note id {note_id!r}", err=True)
        raise typer.Exit(code=2) from exc
    settings = _load_settings(config_path)
    if not settings.mind.enabled:
        typer.echo("selffork mind: Mind is disabled.", err=True)
        raise typer.Exit(code=2)
    asyncio.run(
        _supersede_async(
            settings=settings,
            note_id=nid,
            new_content=new_content,
            new_intent=new_intent,
            project_slug=project,
        ),
    )


async def _supersede_async(
    *,
    settings: SelfForkSettings,
    note_id: UUID,
    new_content: str,
    new_intent: str | None,
    project_slug: str | None,
) -> None:
    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    store = await _open_store(root=root)
    audit = _audit_logger(settings, session_id=_audit_session_id())
    try:
        writer = EpisodicWriter(store=store)
        try:
            old, new = await writer.supersede_decision(
                note_id=note_id,
                new_intent=new_intent if new_intent is not None else "",
                new_body=new_content,
            )
        except ValueError as exc:
            typer.echo(f"selffork mind: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        audit.emit(
            "mind.note.supersede",
            payload={
                "old_id": str(old.id),
                "new_id": str(new.id),
                "valid_until": old.valid_until.isoformat() if old.valid_until else None,
            },
        )
        typer.echo(f"superseded: {old.id}  → new: {new.id}")
    finally:
        await store.teardown()


# ── compact (L1-L3 live in Order 3; --strategy llm preview-only) ──────────


_COMPACT_STRATEGIES: tuple[str, ...] = ("recency", "distill", "cluster", "llm")


@mind_app.command("compact")
def compact_cmd(
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="One of recency/distill/cluster/llm."),
    ] = "recency",
    tier: Annotated[
        str | None,
        typer.Option("--tier", help="Tier to compact (default: all)."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", help="Project to scope."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="Order 2 only allows --dry-run."),
    ] = True,
    config_path: Annotated[
        Path | None,
        typer.Option("--config"),
    ] = None,
) -> None:
    """Run a compaction layer over a tier.

    Order 3 wires real strategies (L1-L3); Order 2 is dry-run only.
    """
    settings = _load_settings(config_path)
    if not settings.mind.enabled:
        typer.echo("selffork mind: Mind is disabled.", err=True)
        raise typer.Exit(code=2)
    if strategy not in _COMPACT_STRATEGIES:
        valid = list(_COMPACT_STRATEGIES)
        typer.echo(
            f"selffork mind: --strategy must be one of {valid}; got {strategy!r}",
            err=True,
        )
        raise typer.Exit(code=2)
    tier_name = _validate_tier(tier)
    if strategy == "llm" and not dry_run:
        typer.echo(
            "selffork mind: live LLM-driven compaction is delegated to "
            "`selffork mind reflect` (Anthropic Auto Dream cycle, ADR-002 §11). "
            "Use --dry-run here to preview the candidate window, then run "
            "`selffork mind reflect` to actually consolidate.",
            err=True,
        )
        raise typer.Exit(code=2)
    asyncio.run(
        _compact_async(
            settings=settings,
            strategy=strategy,
            tier=tier_name,
            project_slug=project,
            dry_run=dry_run,
        ),
    )


async def _compact_async(
    *,
    settings: SelfForkSettings,
    strategy: str,
    tier: TierName | None,
    project_slug: str | None,
    dry_run: bool,
) -> None:
    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    store = await _open_store(root=root)
    audit = _audit_logger(settings, session_id=_audit_session_id())
    try:
        config = RetrieveConfig(
            tiers=(tier,) if tier is not None else (),
            scope=StoreScope(project_slug=project_slug),
            top_k=500,
            rerank_overfetch=1,
        )
        hits = await store.retrieve(config)
        notes = [h.note for h in hits]
        per_tier: dict[str, int] = {}
        for h in hits:
            per_tier[h.note.tier] = per_tier.get(h.note.tier, 0) + 1

        # Build the strategy. ``llm`` is dry-run only at Order 3; Order 5
        # wires it. ``cluster`` uses the store for vector lookups.
        plan_summary: dict[str, object] = {}
        applied_counts: dict[str, int] = {}

        if strategy == "recency":
            plan = await RecencyDecayCompactor().plan(notes=notes)
            plan_summary = dict(plan.summary)
            if not dry_run:
                applied_counts = await apply_plan(plan, store=store, notes=notes)
        elif strategy == "distill":
            # L2 importance distillation + Procedural distiller (T4) — the
            # combined L2-distil pipeline both rebalances importance AND
            # extracts patterns into Procedural. Operator gets one knob.
            #
            # IMPORTANT: ProceduralDistiller.distil() WRITES Procedural
            # notes to the store; gate it behind ``not dry_run`` so the
            # contract on ``--dry-run`` ("zero mutations") holds. L2 plan
            # itself is read-only and always returned.
            l2 = await ImportanceDistiller().plan(notes=notes)
            plan_summary = {"l2": dict(l2.summary)}
            if not dry_run:
                distill_report = await ProceduralDistiller(store=store).distil(
                    project_slug=project_slug,
                )
                plan_summary["procedural"] = distill_report.to_payload()
                applied_counts = await apply_plan(l2, store=store, notes=notes)
            else:
                plan_summary["procedural"] = {
                    "note": "skipped under --dry-run (would write Procedural patterns)",
                }
        elif strategy == "cluster":
            plan = await MedoidClusterCompactor(store=store).plan(notes=notes)
            plan_summary = dict(plan.summary)
            if not dry_run:
                applied_counts = await apply_plan(plan, store=store, notes=notes)
        elif strategy == "llm":
            plan_summary = {
                "reason": (
                    "live LLM compaction is delegated to `selffork mind reflect`; "
                    "this dry-run shows the candidate window only"
                ),
            }
        else:  # pragma: no cover — guarded earlier in the CLI
            plan_summary = {"reason": f"unknown strategy {strategy!r}"}

        audit.emit(
            "mind.compact.run",
            payload={
                "strategy": strategy,
                "tier": tier,
                "project_slug": project_slug,
                "dry_run": dry_run,
                "candidate_count": len(hits),
                "per_tier": per_tier,
                "plan_summary": plan_summary,
                "applied": applied_counts,
            },
        )
        verb = "dry-run" if dry_run else "applied"
        typer.echo(
            f"selffork mind: {verb} {strategy!r}: {len(hits)} candidate(s) across {per_tier}",
        )
        if plan_summary:
            typer.echo(f"  plan: {plan_summary}")
        if applied_counts:
            typer.echo(f"  applied: {applied_counts}")
        if strategy == "llm":
            typer.echo(
                "(live LLM consolidation runs via `selffork mind reflect` — Anthropic Auto Dream.)",
            )
    finally:
        await store.teardown()


# ── reflect (T5 reflection cycle) ─────────────────────────────────────────


@mind_app.command("reflect")
def reflect_cmd(
    project: Annotated[
        str | None,
        typer.Option("--project", help="Project to scope."),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config"),
    ] = None,
) -> None:
    """Run one Anthropic Auto Dream four-phase reflection cycle (T5).

    Deterministic by default. To wire an LLM summariser, construct a
    :class:`~selffork_mind.memory.tiers.Reflector` programmatically with
    a custom ``llm_synth`` callable — the CLI does not invoke an LLM
    autonomously (operator-controlled at all times).
    """
    settings = _load_settings(config_path)
    if not settings.mind.enabled:
        typer.echo("selffork mind: Mind is disabled.", err=True)
        raise typer.Exit(code=2)
    asyncio.run(_reflect_async(settings=settings, project_slug=project))


async def _reflect_async(
    *,
    settings: SelfForkSettings,
    project_slug: str | None,
) -> None:
    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    store = await _open_store(root=root)
    audit = _audit_logger(settings, session_id=_audit_session_id())
    try:
        reflector = Reflector(store=store)
        report = await reflector.reflect(project_slug=project_slug)
        audit.emit(
            "mind.compact.run",
            payload={
                "strategy": "reflect_t5",
                "project_slug": project_slug,
                "report": report.to_payload(),
            },
        )
        typer.echo(f"selffork mind: reflection complete: {report.to_payload()}")
    finally:
        await store.teardown()


# ── stats ─────────────────────────────────────────────────────────────────


@mind_app.command("stats")
def stats_cmd(
    project: Annotated[str | None, typer.Option("--project")] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config"),
    ] = None,
) -> None:
    """Show storage size + per-tier counts + embedder/reranker config."""
    settings = _load_settings(config_path)
    asyncio.run(_stats_async(settings=settings, project_slug=project))


async def _stats_async(
    *,
    settings: SelfForkSettings,
    project_slug: str | None,
) -> None:
    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    db_path = _resolve_db_path(root=root)
    enabled = settings.mind.enabled
    typer.echo(f"enabled:        {enabled}")
    typer.echo(f"storage_root:   {root}")
    typer.echo(f"db_path:        {db_path}")
    if db_path.is_file():
        size_bytes = db_path.stat().st_size
        typer.echo(f"db_size_bytes:  {size_bytes}")
    else:
        typer.echo("db_size_bytes:  (no file yet)")
    typer.echo(f"embedder:       {settings.mind.embedder}")
    typer.echo(f"reranker:       {settings.mind.reranker}")
    typer.echo(f"top_k:          {settings.mind.top_k}")
    typer.echo(f"threshold:      {settings.mind.threshold}")
    if not enabled or not db_path.is_file():
        return
    store = await _open_store(root=root)
    try:
        per_tier: dict[str, int] = {}
        config = RetrieveConfig(
            scope=StoreScope(project_slug=project_slug),
            top_k=10_000,
            rerank_overfetch=1,
        )
        hits = await store.retrieve(config)
        for h in hits:
            per_tier[h.note.tier] = per_tier.get(h.note.tier, 0) + 1
        if not per_tier:
            typer.echo("notes:          (none)")
            return
        typer.echo("notes:")
        for tier, count in sorted(per_tier.items()):
            typer.echo(f"  {tier:<16} {count}")
    finally:
        await store.teardown()


# ── export-corpus (Order 6 three-pillar bridge) ───────────────────────────


@mind_app.command("export-corpus")
def export_corpus_cmd(
    tier: Annotated[
        str,
        typer.Option("--tier", help="Tier to export (typically 'procedural')."),
    ] = "procedural",
    out: Annotated[
        Path,
        typer.Option("--out", help="Output JSONL path."),
    ] = Path("./corpus.jsonl"),
    project: Annotated[
        str | None,
        typer.Option("--project"),
    ] = None,
    interleave: Annotated[
        bool,
        typer.Option(
            "--interleave/--no-interleave",
            help="Bjork desirable difficulty: round-robin across topic groups.",
        ),
    ] = True,
    config_path: Annotated[
        Path | None,
        typer.Option("--config"),
    ] = None,
) -> None:
    """Export a Mind tier as a Reflex-ready fine-tune JSONL corpus.

    Pillar 3 → Pillar 1 bridge (Order 6). Each line is one training
    item with operator-style messages + SM-2 metadata (E-Factor +
    next-review schedule). Bjork desirable difficulties (interleaving)
    are on by default; pass ``--no-interleave`` for canonical order.
    """
    settings = _load_settings(config_path)
    if not settings.mind.enabled:
        typer.echo("selffork mind: Mind is disabled.", err=True)
        raise typer.Exit(code=2)
    tier_name = _validate_tier(tier)
    if tier_name is None:
        raise typer.BadParameter("--tier is required")
    asyncio.run(
        _export_corpus_async(
            settings=settings,
            tier=tier_name,
            out_path=out,
            project_slug=project,
            interleave=interleave,
        ),
    )


async def _export_corpus_async(
    *,
    settings: SelfForkSettings,
    tier: TierName,
    out_path: Path,
    project_slug: str | None,
    interleave: bool,
) -> None:
    from selffork_mind.bridge import ExportConfig, ReflexCorpusExporter

    root = _resolve_mind_root(config=settings.mind, project_slug=project_slug)
    store = await _open_store(root=root)
    audit = _audit_logger(settings, session_id=_audit_session_id())
    try:
        exporter = ReflexCorpusExporter(store=store)
        report = await exporter.export(
            ExportConfig(
                out_path=out_path,
                project_slug=project_slug,
                tiers=(tier,),
                interleave=interleave,
            ),
        )
        audit.emit(
            "mind.compact.run",
            payload={
                "strategy": "export_corpus",
                "report": report.to_payload(),
            },
        )
        typer.echo(f"selffork mind: corpus exported: {report.to_payload()}")
    finally:
        await store.teardown()


@mind_app.command("recall-decision")
def recall_decision_cmd(
    query: Annotated[
        str,
        typer.Argument(..., help="What to recall, e.g. 'heartbeat autonomy'."),
    ],
    decisions_dir: Annotated[
        Path,
        typer.Option("--decisions-dir", help="Directory of ADR / decision markdown files."),
    ] = Path("docs/decisions"),
    archive: Annotated[
        Path | None,
        typer.Option(
            "--archive",
            help="Optional archived decisions SSOT (e.g. docs/archive/Yamac_Jr_Nano_Kararlar.md).",
        ),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option("--top-k", min=1, max=20, help="How many decisions to return."),
    ] = 3,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
) -> None:
    """Recall past operator decisions with ``path:line`` citations (historian).

    Deterministic keyword recall over ``docs/decisions/*.md`` (+ optional
    archive) — no embeddings, no store. Answers "what did we decide about
    X?" and cites the exact ADR + line (see :mod:`selffork_mind.historian`).
    """
    from selffork_mind.historian import Historian

    historian = Historian.from_dir(decisions_dir, archive=archive)
    hits = historian.recall(query, top_k=top_k)
    if as_json:
        typer.echo(
            json.dumps(
                [
                    {
                        "id": hit.decision.id,
                        "title": hit.decision.title,
                        "citation": hit.citation,
                        "score": round(hit.score, 3),
                    }
                    for hit in hits
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if not hits:
        typer.echo(
            f"No decision found for {query!r} "
            f"(indexed {len(historian.decisions)} decisions in {decisions_dir})."
        )
        return
    typer.echo(f"Decisions matching {query!r}:")
    for hit in hits:
        typer.echo(f"  {hit.decision.title}")
        typer.echo(f"    {hit.citation}  (score {hit.score:.1f})")


# ── tiny re-export so tests can construct an ad-hoc app ───────────────────


def build_test_app() -> typer.Typer:
    """Helper for tests — fresh ``mind`` typer instance.

    The module-level :data:`mind_app` is stateful (sub-apps registered at
    import time), but typer treats it as a singleton. Tests sometimes
    want a freshly constructed app to verify command discovery — they
    can grab :data:`mind_app` directly; this helper exists for symmetry
    with the project_app discovery pattern.
    """
    return mind_app


# Public hint for "did the env override the default config?" — used by
# the cli.py boot path so audit logging gains a "mind.cli" namespace.
def env_namespace() -> Literal["mind.cli"]:
    return "mind.cli"


# ── Type checker shim for the embedder factory return ─────────────────────
# The return type of ``_build_embedder`` is ``EmbeddingProvider | None`` at
# runtime, but mypy infers the union from build_embedder's polymorphism.
# We don't import the protocol here because the typer commands only ever
# need it through ``HybridRetriever``.
_ = Any  # silence unused-import warning when only needed transitively
