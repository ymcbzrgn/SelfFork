"""T1 Working — in-context block (Letta pattern).

Per ADR-002 §1: T1 is the smallest, hottest tier — what the operator
needs in-context **right now**. Persona + active project + current task +
free-form scratchpad. Single block per (project_slug, session_id) — every
write replaces the prior block (no history; supersession is implicit
through ``valid_until``).

The block is stored as a single :class:`Note` with ``tier="working"`` and
``kind="pointer"`` — the Note's id is a stable UUID5 derived from
``(project_slug, session_id, "working_block")``, so re-reads always
return the same identity. The body is JSON-serialised
:class:`WorkingBlock` content.

Deliberately small: T1 is the LLM-context-window tax that every round
pays. Letta caps theirs at ~2k tokens; we keep the same intent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from selffork_mind.memory.model import Note
from selffork_mind.memory.tags import Tag
from selffork_mind.store.base import (
    MindStore,
    RetrievalHit,
    RetrieveConfig,
    StoreScope,
)

__all__ = [
    "WorkingBlock",
    "WorkingBlockManager",
]


_BLOCK_INTENT = "working_block"


class WorkingBlock(BaseModel):
    """The hot, in-context block.

    All four sections are optional strings; a fresh block has every
    section empty. The orchestrator decides what to fill.

    - ``persona`` — operator-style stance ("kolaya kaçmayız" mottos).
    - ``active_project`` — project slug + free-text purpose.
    - ``current_task`` — what's open right now (kanban card link or
      free-text plan step).
    - ``scratchpad`` — round-by-round notes; volatile.
    """

    model_config = ConfigDict(extra="forbid")

    persona: str = Field(default="", max_length=4000)
    active_project: str = Field(default="", max_length=400)
    current_task: str = Field(default="", max_length=2000)
    scratchpad: str = Field(default="", max_length=8000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def render(self) -> str:
        """Render as a single human-readable block.

        Used by the orchestrator to inject into the system prompt + by the
        plain-md projection.
        """
        sections: list[tuple[str, str]] = [
            ("persona", self.persona),
            ("active_project", self.active_project),
            ("current_task", self.current_task),
            ("scratchpad", self.scratchpad),
        ]
        lines: list[str] = []
        for name, body in sections:
            if not body:
                continue
            lines.append(f"## {name}")
            lines.append(body)
            lines.append("")
        return "\n".join(lines).rstrip()

    def to_payload(self) -> dict[str, object]:
        return {
            "persona": self.persona,
            "active_project": self.active_project,
            "current_task": self.current_task,
            "scratchpad": self.scratchpad,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> WorkingBlock:
        return cls.model_validate(payload)


class WorkingBlockManager:
    """Reads / writes the T1 Working block for a (project, session) pair.

    The manager is intentionally tiny — its only job is to load the
    persisted block, give the orchestrator a typed object to mutate, and
    persist it back atomically.
    """

    def __init__(self, *, store: MindStore) -> None:
        self._store = store

    async def load(
        self,
        *,
        project_slug: str | None,
        session_id: str | None,
    ) -> WorkingBlock:
        """Fetch the current block; return an empty :class:`WorkingBlock`
        when none exists yet.
        """
        hits = await self._fetch(project_slug=project_slug, session_id=session_id)
        if not hits:
            return WorkingBlock()
        # Deterministic identity: there should be at most one currently-
        # valid working block per scope. Pick the most recent valid_from.
        hits.sort(key=lambda h: h.note.valid_from, reverse=True)
        try:
            payload = json.loads(hits[0].note.content)
        except (json.JSONDecodeError, ValueError):
            return WorkingBlock()
        try:
            return WorkingBlock.from_payload(payload)
        except (ValueError, TypeError):
            return WorkingBlock()

    async def save(
        self,
        block: WorkingBlock,
        *,
        project_slug: str | None,
        session_id: str | None,
    ) -> Note:
        """Persist the block; supersedes any prior block for this scope."""
        moment = datetime.now(UTC)
        updated = block.model_copy(update={"updated_at": moment})
        body = json.dumps(updated.to_payload(), ensure_ascii=False, sort_keys=True)
        note = Note(
            tier="working",
            kind="pointer",
            content=body,
            intent=_BLOCK_INTENT,
            project_slug=project_slug,
            session_id=session_id,
            importance=10.0,  # always fresh
            pinned=True,  # never evicted by compaction
        )
        # Supersede any prior valid block before write so reads after this
        # method return the new one alone.
        prior = await self._fetch(project_slug=project_slug, session_id=session_id)
        for hit in prior:
            await self._store.supersede(hit.note.id, at=moment)
        stored = await self._store.upsert_note(note)
        tags = self._tags_for_block(stored, project_slug=project_slug, session_id=session_id)
        if tags:
            await self._store.attach_tags(tags)
        return stored

    async def clear(
        self,
        *,
        project_slug: str | None,
        session_id: str | None,
    ) -> None:
        """Supersede every working block for the scope.

        Equivalent to writing an empty block but skips the new write — use
        when starting a fresh session and you want T1 to be empty.
        """
        moment = datetime.now(UTC)
        prior = await self._fetch(project_slug=project_slug, session_id=session_id)
        for hit in prior:
            await self._store.supersede(hit.note.id, at=moment)

    async def patch(
        self,
        *,
        project_slug: str | None,
        session_id: str | None,
        persona: str | None = None,
        active_project: str | None = None,
        current_task: str | None = None,
        scratchpad: str | None = None,
    ) -> WorkingBlock:
        """Read-modify-save in one call.

        ``None`` means "leave the field unchanged"; pass an empty string
        to clear a field.
        """
        block = await self.load(project_slug=project_slug, session_id=session_id)
        updates: dict[str, object] = {}
        if persona is not None:
            updates["persona"] = persona
        if active_project is not None:
            updates["active_project"] = active_project
        if current_task is not None:
            updates["current_task"] = current_task
        if scratchpad is not None:
            updates["scratchpad"] = scratchpad
        if not updates:
            return block
        next_block = block.model_copy(update=updates)
        await self.save(next_block, project_slug=project_slug, session_id=session_id)
        return next_block

    async def _fetch(
        self,
        *,
        project_slug: str | None,
        session_id: str | None,
    ) -> list[RetrievalHit]:
        config = RetrieveConfig(
            tiers=("working",),
            scope=StoreScope(project_slug=project_slug, session_id=session_id),
            top_k=10,
            rerank_overfetch=1,
        )
        return list(await self._store.retrieve(config))

    @staticmethod
    def _tags_for_block(
        note: Note,
        *,
        project_slug: str | None,
        session_id: str | None,
    ) -> list[Tag]:
        tags: list[Tag] = []
        if project_slug is not None:
            tags.append(Tag.now(note_id=note.id, key="project", value=project_slug))
        if session_id is not None:
            tags.append(Tag.now(note_id=note.id, key="session", value=session_id))
        tags.append(Tag.now(note_id=note.id, key="kind", value="working_block"))
        return tags
