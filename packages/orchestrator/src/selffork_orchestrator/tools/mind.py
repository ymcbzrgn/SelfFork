"""Mind-aware tools — ``mind_recall`` + ``mind_note_add``.

Per ``project_jr_tool_protocol.md``, SelfFork Jr emits structured tool
calls. Order 2 wires two new tools so Jr can recall past memories
mid-session and capture insights without leaving the round loop:

- ``mind_recall(query, top_k, tier)`` — runs the
  :class:`HybridRetriever` and returns hits.
- ``mind_note_add(content, tier, intent, tag_pairs)`` — writes a Mind
  note via the active :class:`EpisodicWriter`.

Both tools require the orchestrator to wire the relevant collaborators
into :class:`ToolContext` at registry construction time. When Mind is
disabled at boot, the tools return :data:`unauthorized` rather than
raising — so Jr sees a clean error and can adapt without crashing the
session.

Handlers are async — they bridge directly to the async Mind APIs. The
registry's :meth:`~ToolRegistry.invoke_async` method awaits them; sync
call sites that try :meth:`~ToolRegistry.invoke` against an async
handler get a clear ``handler_error`` envelope instead of a runtime
crash.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from selffork_mind.memory.tiers import EpisodicWriter
from selffork_mind.rag.retriever import HybridRetriever
from selffork_mind.store.base import MindStore, StoreScope
from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolContext,
    ToolSpec,
    raise_unauthorized,
)

__all__ = ["build_mind_tools"]


_VALID_TIERS = {
    "working",
    "episodic",
    "semantic_graph",
    "procedural",
    "reflection",
    "recall",
}


# ── mind_recall ────────────────────────────────────────────────────────────


class _MindRecallArgs(ToolArgs):
    """Args for ``mind_recall``."""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    tier: str | None = Field(default=None)
    threshold: float = Field(default=0.0, ge=0.0, le=1.0)


async def _mind_recall_handler(
    ctx: ToolContext,
    args: _MindRecallArgs,
) -> dict[str, Any]:
    retriever = ctx.mind_retriever
    if retriever is None:
        raise_unauthorized(
            "mind_recall requires Mind to be enabled (mind_retriever is None). "
            "Set mind.enabled=true in selffork.yaml.",
        )
    if args.tier is not None and args.tier not in _VALID_TIERS:
        return {
            "error": (f"unknown tier {args.tier!r}; expected one of {sorted(_VALID_TIERS)}"),
            "hits": [],
        }
    if not isinstance(retriever, HybridRetriever):
        return {"error": "mind_retriever wired but is not a HybridRetriever", "hits": []}

    tiers: tuple[str, ...] = (args.tier,) if args.tier is not None else ()
    hits = await retriever.recall(
        query=args.query,
        scope=StoreScope(
            project_slug=ctx.project_slug,
            session_id=None,
            cli_agent=None,
        ),
        tiers=tiers,  # type: ignore[arg-type]
        top_k=args.top_k,
        threshold=args.threshold,
        session_id=ctx.session_id,
        project_slug=ctx.project_slug,
    )
    hits_payload = [
        {
            "id": str(h.note.id),
            "tier": h.note.tier,
            "kind": h.note.kind,
            "score": float(h.score),
            "intent": h.note.intent,
            "content": h.note.content,
            "project_slug": h.note.project_slug,
            "session_id": h.note.session_id,
        }
        for h in hits
    ]
    return {
        "query": args.query,
        "top_k": args.top_k,
        "tier": args.tier,
        "hits": hits_payload,
        "hit_count": len(hits_payload),
    }


# ── mind_note_add ──────────────────────────────────────────────────────────


_VALID_KINDS = {"decision", "observation", "pattern", "reflection", "pointer"}


class _MindNoteAddArgs(ToolArgs):
    """Args for ``mind_note_add``."""

    content: str = Field(..., min_length=1)
    tier: str = Field(default="episodic")
    kind: str = Field(default="observation")
    intent: str = Field(default="", max_length=200)
    tag_pairs: list[list[str]] = Field(
        default_factory=list,
        description="List of [key, value] pairs.",
    )
    importance: float = Field(default=1.0, ge=0.0, le=10.0)
    pinned: bool = Field(default=False)


async def _mind_note_add_handler(
    ctx: ToolContext,
    args: _MindNoteAddArgs,
) -> dict[str, Any]:
    if ctx.mind_store is None or ctx.episodic_writer is None:
        raise_unauthorized(
            "mind_note_add requires Mind to be enabled (mind_store / "
            "episodic_writer is None). Set mind.enabled=true in selffork.yaml.",
        )
    mind_store = ctx.mind_store
    if not isinstance(mind_store, MindStore):
        return {"error": "mind_store wired but is not a MindStore"}
    episodic_writer = ctx.episodic_writer
    if not isinstance(episodic_writer, EpisodicWriter):
        return {"error": "episodic_writer wired but is not an EpisodicWriter"}
    if args.tier not in _VALID_TIERS:
        return {
            "error": f"unknown tier {args.tier!r}; expected one of {sorted(_VALID_TIERS)}",
        }
    if args.kind not in _VALID_KINDS:
        return {
            "error": f"unknown kind {args.kind!r}; expected one of {sorted(_VALID_KINDS)}",
        }
    parsed_pairs: list[tuple[str, str]] = []
    for pair in args.tag_pairs:
        if len(pair) != 2:
            return {"error": f"tag_pairs entries must be [key, value]; got {pair!r}"}
        key, value = pair[0], pair[1]
        if not key or not value:
            return {"error": "tag_pairs entries cannot have empty key or value"}
        parsed_pairs.append((key, value))

    # write_decision's natural default importance is 5.0 (decisions are
    # weighty); only forward an explicit override (>1.0 means the operator
    # bumped it themselves; 1.0 is the args' default and we keep the
    # write_decision default in that case).
    decision_importance: float | None = args.importance if args.importance != 1.0 else None

    # Use write_decision when kind=decision (carries higher default importance + audit-ready
    # semantics). Otherwise write a single-note round-style observation: we fake a one-side
    # conversation — operator_message is the content, cli_response is empty.
    if args.kind == "decision":
        note = await episodic_writer.write_decision(
            session_id=ctx.session_id,
            intent=args.intent,
            body=args.content,
            project_slug=ctx.project_slug,
            importance=decision_importance if decision_importance is not None else 5.0,
        )
        stored_notes = [note]
    else:
        stored_notes = await episodic_writer.write_round(
            session_id=ctx.session_id,
            project_slug=ctx.project_slug,
            cli_agent=ctx.cli_agent_name,
            round_index=0,
            operator_message=args.content,
            cli_response="",
        )
    if parsed_pairs:
        from selffork_mind.memory.tags import Tag  # local import: avoid cycle in stub paths

        extra_tags = [
            Tag.now(note_id=n.id, key=k, value=v) for n in stored_notes for k, v in parsed_pairs
        ]
        await mind_store.attach_tags(extra_tags)
    return {
        "ids": [str(n.id) for n in stored_notes],
        "tier": stored_notes[0].tier,
        "kind": stored_notes[0].kind,
        "tag_count": len(parsed_pairs),
    }


# ── Registry helper ────────────────────────────────────────────────────────


def build_mind_tools() -> list[ToolSpec[Any]]:
    """Return the canonical Mind tools.

    Caller registers them via :class:`ToolRegistry` (typically through
    ``build_default_registry``).
    """
    return [
        ToolSpec(
            name="mind_recall",
            description=(
                "Recall past Mind notes (episodic / decisions / patterns / "
                "reflections) by semantic + lexical hybrid search. "
                "Returns the top-k hits with score + content."
            ),
            args_model=_MindRecallArgs,
            handler=_mind_recall_handler,
        ),
        ToolSpec(
            name="mind_note_add",
            description=(
                "Write a single Mind note. Use kind=decision for "
                "operator-style choices, observation for facts, pattern "
                "for distilled reflexes."
            ),
            args_model=_MindNoteAddArgs,
            handler=_mind_note_add_handler,
        ),
    ]
