"""T2 Episodic — per-round writer for the round-loop hot path.

Per ADR-002 §1: T2 is "per-session events (rounds, tool calls, sentinels)"
written from the orchestrator round loop. The writer is deliberately thin:
each call corresponds to one orchestrator round, and the deterministic
bypass (Cognee pattern) means structured signals (tool calls, sentinels)
become typed Notes 1:1 without any LLM extraction.

Writes:

- One **observation** Note per round, capturing operator → CLI exchange
  (``content`` is the rendered round text; ``intent`` is ``"round N"``).
- One **pattern** Note per tool call (Cognee deterministic bypass: tool
  calls are structured triples 1:1).
- Tag set per Note: ``project / session / cli / round / kind`` plus any
  detected sentinel (``[SELFFORK:DONE]``, ``[SELFFORK:SPAWN:`` …).

When constructed with an embedder, every written Note is embedded and the
vector is attached via :meth:`MindStore.attach_embedding` so downstream
retrievers (Order 2.3 +) can do cosine similarity. When the embedder is
``None``, no vectors are computed (graceful degradation).

Decisions are written via :meth:`write_decision`; superseding a decision
uses the bi-temporal Graphiti pattern (validity-window stamping, no
in-place mutation).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from selffork_mind.memory.model import Note
from selffork_mind.memory.tags import Tag
from selffork_mind.projections.markdown import MarkdownProjection
from selffork_mind.rag.embedder import EmbeddingProvider
from selffork_mind.store.base import (
    MindStore,
    RetrieveConfig,
    StoreScope,
)

__all__ = [
    "EpisodicToolCall",
    "EpisodicWriter",
    "detect_sentinels",
]


@dataclass(frozen=True, slots=True)
class EpisodicToolCall:
    """Slim tool-call record handed to :meth:`EpisodicWriter.write_round`.

    The orchestrator's ``selffork_orchestrator.tools.base.ToolCall`` +
    ``ToolResult`` types are pillar-internal; T2 takes a neutral,
    boundary-friendly snapshot instead.
    """

    tool: str
    args: dict[str, object]
    status: str
    """One of ``ok / invalid_args / unknown_tool / handler_error / unauthorized``."""
    result_payload: dict[str, object] | None = None
    error: str | None = None


_SENTINEL_PREFIXES: tuple[str, ...] = (
    "[SELFFORK:DONE]",
    "[SELFFORK:SPAWN:",
)


def detect_sentinels(text: str) -> list[str]:
    """Return the literal sentinel substrings found in ``text``.

    Substring match — never regex — to match
    ``project_done_sentinel_protocol.md``. ``[SELFFORK:SPAWN:`` matches a
    family (e.g. ``[SELFFORK:SPAWN: foo]``); we record the prefix only,
    so the tag set stays small + comparable.
    """
    return [s for s in _SENTINEL_PREFIXES if s in text]


class EpisodicWriter:
    """Per-round T2 Episodic writer.

    Single-process; not multi-writer safe (write fan-out should happen
    upstream of one writer instance per session).

    When constructed with a :class:`MarkdownProjection`, every successful
    write triggers a deterministic projection refresh — the operator gets
    transparent on-disk MEMORY.md + topic files (Anthropic / Cursor 2.1
    lesson; ADR-002 §7). Projection failures are logged but never block
    the canonical store write.
    """

    def __init__(
        self,
        *,
        store: MindStore,
        embedder: EmbeddingProvider | None = None,
        projection: MarkdownProjection | None = None,
        projection_scope: StoreScope | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._projection = projection
        self._projection_scope = projection_scope or StoreScope()

    @property
    def embedder(self) -> EmbeddingProvider | None:
        return self._embedder

    @property
    def projection(self) -> MarkdownProjection | None:
        return self._projection

    async def write_round(
        self,
        *,
        session_id: str,
        project_slug: str | None,
        cli_agent: str | None,
        round_index: int,
        operator_message: str,
        cli_response: str,
        tool_calls: Sequence[EpisodicToolCall] = (),
        sentinels: Sequence[str] | None = None,
        path_scope: tuple[str, ...] = (),
    ) -> list[Note]:
        """Capture one round.

        Returns the persisted notes in deterministic order: the observation
        note first, then one pattern note per tool call (matching the order
        of ``tool_calls``).

        ``sentinels`` is auto-detected from ``operator_message`` when
        ``None``. Pass an explicit list (possibly empty) to bypass detection
        — useful when the orchestrator already parsed the reply and wants
        to attach extra sentinels (e.g. spawn target).
        """
        detected = list(sentinels) if sentinels is not None else detect_sentinels(operator_message)
        importance = 1.0 + (0.5 if detected else 0.0)

        observation = Note(
            tier="episodic",
            kind="observation",
            content=_render_round_content(operator_message, cli_response),
            intent=f"round {round_index}",
            project_slug=project_slug,
            session_id=session_id,
            source_pointer=f"audit:{session_id}:round:{round_index}",
            path_scope=path_scope,
            importance=importance,
        )

        notes_to_write: list[Note] = [observation]
        for tc in tool_calls:
            notes_to_write.append(
                Note(
                    tier="episodic",
                    kind="pattern",
                    content=_render_tool_call_content(tc),
                    intent=f"tool:{tc.tool}",
                    project_slug=project_slug,
                    session_id=session_id,
                    source_pointer=(f"audit:{session_id}:round:{round_index}:tool:{tc.tool}"),
                    path_scope=path_scope,
                ),
            )

        stored = await self._store.upsert_notes(notes_to_write)

        tags: list[Tag] = []
        for note in stored:
            for key, value in _tags_for_note(
                note,
                cli_agent=cli_agent,
                round_index=round_index,
                sentinels=detected,
            ):
                tags.append(Tag.now(note_id=note.id, key=key, value=value))
        if tags:
            await self._store.attach_tags(tags)

        await self._maybe_embed(stored)
        await self.project_markdown()
        return stored

    async def write_decision(
        self,
        *,
        session_id: str | None,
        intent: str,
        body: str,
        project_slug: str | None,
        path_scope: tuple[str, ...] = (),
        importance: float = 5.0,
    ) -> Note:
        """Write one ``decision``-kind Note.

        Decisions carry above-baseline ``importance`` by default (5 vs the
        observation default of 1) so the recency-decay scorer surfaces them
        even after weeks. Superseding decisions uses
        :meth:`supersede_decision`.
        """
        note = Note(
            tier="episodic",
            kind="decision",
            content=body,
            intent=intent,
            project_slug=project_slug,
            session_id=session_id,
            path_scope=path_scope,
            importance=importance,
        )
        stored = await self._store.upsert_note(note)

        tags: list[Tag] = []
        if project_slug is not None:
            tags.append(Tag.now(note_id=stored.id, key="project", value=project_slug))
        if session_id is not None:
            tags.append(Tag.now(note_id=stored.id, key="session", value=session_id))
        tags.append(Tag.now(note_id=stored.id, key="kind", value="decision"))
        if tags:
            await self._store.attach_tags(tags)

        await self._maybe_embed([stored])
        await self.project_markdown()
        return stored

    async def supersede_decision(
        self,
        *,
        note_id: UUID,
        new_intent: str,
        new_body: str,
        importance: float | None = None,
    ) -> tuple[Note, Note]:
        """Mark old decision superseded; write a new one. Returns ``(old, new)``.

        Bi-temporal validity (Graphiti pattern, ADR-002 §6): the old note's
        ``valid_until`` is stamped to ``now``; a new note (same project,
        same session) is written with the new content. The old note is
        never mutated in place.

        Raises ``ValueError`` if the source note is missing or isn't a
        decision (we'd rather fail loudly than silently degrade the
        decision audit).
        """
        old = await self._store.get_note(note_id)
        if old is None:
            raise ValueError(f"note {note_id} not found")
        if old.kind != "decision":
            raise ValueError(
                f"note {note_id} is not a decision (kind={old.kind!r})",
            )

        moment = datetime.now(UTC)
        old_updated = await self._store.supersede(note_id, at=moment)
        if old_updated is None:
            raise ValueError(f"failed to supersede {note_id}")

        new = await self.write_decision(
            session_id=old.session_id,
            intent=new_intent,
            body=new_body,
            project_slug=old.project_slug,
            path_scope=old.path_scope,
            importance=importance if importance is not None else old.importance,
        )
        return old_updated, new

    async def _maybe_embed(self, notes: Sequence[Note]) -> None:
        if self._embedder is None:
            return
        if not notes:
            return
        texts = [n.content for n in notes]
        vectors = await self._embedder.embed(texts)
        embedder_name = self._embedder.name
        for note, vector in zip(notes, vectors, strict=True):
            await self._store.attach_embedding(
                note_id=note.id,
                vector=vector,
                embedder_name=embedder_name,
            )

    async def project_markdown(self) -> None:
        """Refresh the markdown projection from the canonical store.

        No-op when no projection is wired. Reads up to 500 notes through
        the projection scope (project / session) and rewrites the index +
        topic files on disk. Best-effort: errors are swallowed so
        projection never blocks the round loop.
        """
        if self._projection is None:
            return
        try:
            hits = await self._store.retrieve(
                RetrieveConfig(
                    scope=self._projection_scope,
                    top_k=500,
                    rerank_overfetch=1,
                ),
            )
            self._projection.write([h.note for h in hits])
        except Exception:
            # Projection is observability — never break the writer.
            return


# ── module helpers ────────────────────────────────────────────────────────


def _render_round_content(operator_message: str, cli_response: str) -> str:
    return f"operator: {operator_message}\n\ncli: {cli_response}"


def _render_tool_call_content(tc: EpisodicToolCall) -> str:
    payload: dict[str, object] = {
        "tool": tc.tool,
        "args": tc.args,
        "status": tc.status,
    }
    if tc.result_payload is not None:
        payload["result"] = tc.result_payload
    if tc.error is not None:
        payload["error"] = tc.error
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tags_for_note(
    note: Note,
    *,
    cli_agent: str | None,
    round_index: int,
    sentinels: Sequence[str],
) -> list[tuple[str, str]]:
    tags: list[tuple[str, str]] = []
    if note.project_slug is not None:
        tags.append(("project", note.project_slug))
    if note.session_id is not None:
        tags.append(("session", note.session_id))
    if cli_agent is not None:
        tags.append(("cli", cli_agent))
    tags.append(("round", str(round_index)))
    tags.append(("kind", note.kind))
    for sentinel in sentinels:
        tags.append(("sentinel", sentinel))
    return tags
