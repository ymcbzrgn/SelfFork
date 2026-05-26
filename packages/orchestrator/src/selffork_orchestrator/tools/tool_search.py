"""RAG-over-tools seam (S-ToolFleet Faz 0).

When the tool fleet grows past ~30-50 specs (Anthropic empirical
degradation threshold; RAG-MCP / Tool-to-Agent / Anthropic Tool Search
literature), keeping every tool's name + description + args schema
inline in the system prompt blows out context AND degrades the model's
selection accuracy. Anthropic's published mitigation: mark non-default
tools with ``defer_loading=True`` so they're omitted from the eager
prompt, then expose a ``tool_search`` meta-tool the model can call to
discover deferred tools when a task needs them.

This module ships the search side of that seam:

* :class:`ToolCatalogRetriever` — BM25-Okapi over ``name + description``
  of every deferred ToolSpec in a :class:`~tools.base.ToolRegistry`. The
  same ``rank_bm25`` dep Mind already pulls in (no new requirement).
* :func:`handle_tool_search` — async handler the registered ``tool_search``
  tool routes to. Returns the top-K deferred specs (or all specs when
  ``include_eager=True``) as a list of ``{name, description, args_schema}``
  dicts — same shape :meth:`ToolRegistry.catalog` already produces so the
  result splices cleanly into Self Jr's next-round context.
* :func:`build_tool_search_spec` — factory the default registry imports
  in ``tools/__init__.py``.

Faz 0 ships the SEAM: ``defer_loading=False`` on every existing spec so
behaviour is unchanged. Faz 1+ tool-fleet expansion sets the flag on the
~120 mobile / ~60 browser / ~40 cross-cutting / ~25 VR/AR tools and
relies on this retriever to keep the eager prompt under ~30 entries.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field
from rank_bm25 import BM25Okapi

from selffork_orchestrator.tools.base import (
    ToolContext,
    ToolRegistry,
    ToolSpec,
)

__all__ = [
    "ToolCatalogRetriever",
    "ToolSearchArgs",
    "build_tool_search_spec",
    "handle_tool_search",
]

_log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def _tokenise(text: str) -> list[str]:
    """Split on non-word chars, lowercase. Mirrors :mod:`mind.rag.scoring`."""
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


class ToolCatalogRetriever:
    """BM25-Okapi search over a registry's deferred tool specs.

    Built once per call (no caching) — the registry can mutate between
    rounds and the corpus is small (10s of tools today, ~300 ceiling
    per the S-ToolFleet plan), so rebuild cost is negligible.

    Both ``deferred_only`` and ``include_eager=False`` paths are
    supported: eager tools live in the system prompt already, so the
    default returns the deferred subset only.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        include_eager: bool = False,
    ) -> None:
        self._registry = registry
        self._include_eager = include_eager
        self._specs: list[ToolSpec[Any]] = self._gather_specs()
        # Cache per-spec token lists for the overlap tie-breaker —
        # BM25Okapi alone gives 0 scores on very small corpora where
        # every token's IDF collapses (N=2 and df=1 → log(1) = 0). The
        # overlap signal keeps the retriever useful both in tests
        # (tiny corpus) and in production (~300 tools at Faz 1+).
        self._doc_tokens: list[list[str]] = [
            self._tokens_for(spec) for spec in self._specs
        ]
        self._bm25: BM25Okapi | None = None
        if self._specs:
            self._bm25 = BM25Okapi(self._doc_tokens)

    def _gather_specs(self) -> list[ToolSpec[Any]]:
        if self._include_eager:
            return [
                spec for name in self._registry.names()
                if (spec := self._registry.get(name)) is not None
            ]
        return self._registry.deferred_specs()

    @staticmethod
    def _tokens_for(spec: ToolSpec[Any]) -> list[str]:
        """Combine name + description tokens. Empty doc still gets the name."""
        tokens = _tokenise(spec.name) + _tokenise(spec.description)
        if not tokens:
            # BM25Okapi crashes on empty docs — sentinel keeps the corpus
            # valid; the spec just won't score above zero for any query.
            tokens = ["__empty__"]
        return tokens

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[ToolSpec[Any]]:
        """Return up to ``top_k`` specs ranked by BM25 + overlap tie-breaker.

        Score = BM25_okapi + 0.01 * |query_tokens ∩ doc_tokens|.

        The overlap term keeps the retriever useful when BM25's IDF
        flattens out (small corpus or tokens appearing in most docs).
        Specs with zero overlap AND zero BM25 score are dropped —
        no shared signal with the query, so returning them dilutes the
        result. Ties break by ``spec.name`` for deterministic ordering.
        """
        if top_k <= 0:
            return []
        if self._bm25 is None or not self._specs:
            return []
        query_tokens = _tokenise(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        query_set = set(query_tokens)
        ranked: list[tuple[float, ToolSpec[Any]]] = []
        for score, spec, doc_tokens in zip(
            scores, self._specs, self._doc_tokens, strict=True,
        ):
            overlap = len(query_set & set(doc_tokens))
            if overlap == 0 and float(score) <= 0:
                continue
            combined = float(score) + overlap * 0.01
            ranked.append((combined, spec))
        ranked.sort(key=lambda item: (-item[0], item[1].name))
        return [spec for _score, spec in ranked[:top_k]]


# ── tool spec ─────────────────────────────────────────────────────────


class ToolSearchArgs(BaseModel):
    """Args for the ``tool_search`` meta-tool."""

    model_config = ConfigDict(extra="ignore")

    query: Annotated[str, Field(min_length=1, max_length=2000)]
    top_k: Annotated[int, Field(ge=1, le=20)] = 5
    include_eager: bool = False


async def handle_tool_search(
    ctx: ToolContext,
    args: ToolSearchArgs,
) -> dict[str, Any]:
    """RAG-over-tools handler — return deferred specs matching ``query``.

    Result shape mirrors :meth:`ToolRegistry.catalog` so Self Jr can
    splice the response into its context exactly like the eager tool
    list.

    Statuses:

    * ``status="ok"`` — zero or more matching specs in ``results``.
    * ``status="unwired"`` — ``ctx.tool_registry`` is missing (test
      contexts or legacy code paths). Self Jr learns the capability is
      absent rather than crashing.
    """
    registry = ctx.tool_registry
    if not isinstance(registry, ToolRegistry):
        return {
            "status": "unwired",
            "query": args.query,
            "results": [],
            "message": (
                "tool_search requires a ToolRegistry on ToolContext; "
                "the orchestrator did not wire one."
            ),
        }

    retriever = ToolCatalogRetriever(
        registry, include_eager=args.include_eager,
    )
    specs = retriever.search(args.query, top_k=args.top_k)
    results = [
        {
            "name": spec.name,
            "description": spec.description,
            "args_schema": spec.json_schema(),
        }
        for spec in specs
    ]
    _log.info(
        "tool_search",
        extra={
            "query_len": len(args.query),
            "top_k": args.top_k,
            "include_eager": args.include_eager,
            "matches": len(results),
        },
    )
    return {
        "status": "ok",
        "query": args.query,
        "results": results,
        "matches": len(results),
    }


def build_tool_search_spec() -> ToolSpec[ToolSearchArgs]:
    """Factory imported by :mod:`tools.__init__.build_default_registry`."""
    return ToolSpec(
        name="tool_search",
        description=(
            "Search the deferred-tool corpus for capabilities not "
            "currently visible in the system prompt. Use when the "
            "task needs a tool you can't see — pass a short natural-"
            "language description of what you need (e.g. 'send a "
            "Slack message', 'list iOS apps'). Returns up to top_k "
            "matching specs ranked by BM25 over name + description."
        ),
        args_model=ToolSearchArgs,
        handler=handle_tool_search,
    )
