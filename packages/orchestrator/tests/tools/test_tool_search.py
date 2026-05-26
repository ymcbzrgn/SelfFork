"""Tests for the RAG-over-tools seam (S-ToolFleet Faz 0)."""

from __future__ import annotations

from typing import Any

import pytest

from selffork_orchestrator.tools import build_default_registry
from selffork_orchestrator.tools.base import (
    ToolArgs,
    ToolCall,
    ToolContext,
    ToolRegistry,
    ToolSpec,
)
from selffork_orchestrator.tools.tool_search import (
    ToolCatalogRetriever,
    ToolSearchArgs,
    handle_tool_search,
)

# ── helpers ────────────────────────────────────────────────────────────


class _EmptyArgs(ToolArgs):
    pass


def _spec(
    name: str, description: str, *, defer_loading: bool = False,
) -> ToolSpec[_EmptyArgs]:
    async def _handler(
        ctx: ToolContext, args: _EmptyArgs,
    ) -> dict[str, Any]:
        return {"status": "ok"}

    return ToolSpec(
        name=name,
        description=description,
        args_model=_EmptyArgs,
        handler=_handler,
        defer_loading=defer_loading,
    )


def _ctx(*, registry: ToolRegistry | None) -> ToolContext:
    return ToolContext(
        session_id="sess-test",
        project_slug=None,
        project_store=object(),
        tool_registry=registry,
    )


# ── ToolSpec.defer_loading + Registry helpers ─────────────────────────


def test_spec_defaults_defer_loading_false() -> None:
    spec = _spec("alpha", "do alpha things")
    assert spec.defer_loading is False


def test_spec_accepts_defer_loading_true() -> None:
    spec = _spec("alpha", "do alpha things", defer_loading=True)
    assert spec.defer_loading is True


def test_registry_eager_names_excludes_deferred() -> None:
    eager = _spec("eager_one", "eager doc")
    deferred = _spec("deferred_one", "deferred doc", defer_loading=True)
    registry = ToolRegistry(specs=[eager, deferred])
    assert registry.eager_names() == ["eager_one"]
    assert registry.deferred_names() == ["deferred_one"]


def test_registry_catalog_include_deferred_default_true() -> None:
    eager = _spec("eager_one", "eager doc")
    deferred = _spec("deferred_one", "deferred doc", defer_loading=True)
    registry = ToolRegistry(specs=[eager, deferred])
    full = registry.catalog()
    assert {entry["name"] for entry in full} == {"eager_one", "deferred_one"}


def test_registry_catalog_include_deferred_false_skips_deferred() -> None:
    eager = _spec("eager_one", "eager doc")
    deferred = _spec("deferred_one", "deferred doc", defer_loading=True)
    registry = ToolRegistry(specs=[eager, deferred])
    eager_only = registry.catalog(include_deferred=False)
    assert {entry["name"] for entry in eager_only} == {"eager_one"}


def test_registry_deferred_specs_returns_spec_instances() -> None:
    eager = _spec("eager_one", "eager doc")
    deferred = _spec("deferred_one", "deferred doc", defer_loading=True)
    registry = ToolRegistry(specs=[eager, deferred])
    specs = registry.deferred_specs()
    assert len(specs) == 1
    assert specs[0].name == "deferred_one"


# ── ToolCatalogRetriever (BM25) ────────────────────────────────────────


def test_retriever_returns_empty_on_empty_corpus() -> None:
    registry = ToolRegistry(specs=[])
    retriever = ToolCatalogRetriever(registry)
    assert retriever.search("anything") == []


def test_retriever_returns_empty_when_no_deferred() -> None:
    eager = _spec("eager_one", "eager doc")
    registry = ToolRegistry(specs=[eager])
    retriever = ToolCatalogRetriever(registry)
    # include_eager=False (default) → eager tools excluded → empty
    assert retriever.search("eager") == []


def test_retriever_includes_eager_when_flag_set() -> None:
    eager = _spec("eager_one", "eager doc about widgets")
    deferred = _spec("deferred_one", "deferred about gadgets", defer_loading=True)
    registry = ToolRegistry(specs=[eager, deferred])
    retriever = ToolCatalogRetriever(registry, include_eager=True)
    results = retriever.search("widgets")
    assert len(results) == 1
    assert results[0].name == "eager_one"


def test_retriever_ranks_by_bm25_score() -> None:
    specs = [
        _spec("slack_send", "send a Slack message", defer_loading=True),
        _spec("email_send", "send an email message", defer_loading=True),
        _spec("github_pr_open", "open a pull request on GitHub", defer_loading=True),
    ]
    registry = ToolRegistry(specs=specs)
    retriever = ToolCatalogRetriever(registry)
    results = retriever.search("send slack")
    assert len(results) >= 1
    # slack_send must outrank github_pr_open (no shared tokens).
    names = [s.name for s in results]
    assert "slack_send" in names
    assert "github_pr_open" not in names


def test_retriever_top_k_caps_results() -> None:
    specs = [
        _spec(f"action_{i}", f"do action number {i}", defer_loading=True)
        for i in range(10)
    ]
    registry = ToolRegistry(specs=specs)
    retriever = ToolCatalogRetriever(registry)
    results = retriever.search("action", top_k=3)
    assert len(results) == 3


def test_retriever_drops_zero_score_specs() -> None:
    specs = [
        _spec("slack_send", "send a Slack message", defer_loading=True),
        _spec("github_pr_open", "open a pull request on GitHub", defer_loading=True),
    ]
    registry = ToolRegistry(specs=specs)
    retriever = ToolCatalogRetriever(registry)
    # Query has no token overlap with github_pr_open.
    results = retriever.search("slack")
    names = [s.name for s in results]
    assert names == ["slack_send"]


def test_retriever_empty_query_returns_empty() -> None:
    specs = [_spec("slack_send", "send a Slack message", defer_loading=True)]
    registry = ToolRegistry(specs=specs)
    retriever = ToolCatalogRetriever(registry)
    assert retriever.search("") == []
    assert retriever.search("   ") == []


def test_retriever_top_k_zero_or_negative_returns_empty() -> None:
    specs = [_spec("slack_send", "send a Slack message", defer_loading=True)]
    registry = ToolRegistry(specs=specs)
    retriever = ToolCatalogRetriever(registry)
    assert retriever.search("slack", top_k=0) == []
    assert retriever.search("slack", top_k=-1) == []


def test_retriever_tolerates_empty_description() -> None:
    # rank_bm25 crashes on empty corpora rows — the retriever swaps in
    # a sentinel token so the spec stays in the index (but never
    # matches a real query).
    spec = _spec("blank", "", defer_loading=True)
    registry = ToolRegistry(specs=[spec])
    retriever = ToolCatalogRetriever(registry)
    # The spec name "blank" is tokenised, so a query of "blank" matches.
    results = retriever.search("blank")
    assert len(results) == 1
    assert results[0].name == "blank"


# ── handle_tool_search ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_tool_search_unwired_when_registry_missing() -> None:
    ctx = _ctx(registry=None)
    args = ToolSearchArgs(query="anything")
    result = await handle_tool_search(ctx, args)
    assert result["status"] == "unwired"
    assert result["results"] == []


@pytest.mark.asyncio
async def test_handle_tool_search_returns_matching_specs() -> None:
    specs = [
        _spec("slack_send", "send a Slack message", defer_loading=True),
        _spec("email_send", "send an email", defer_loading=True),
    ]
    registry = ToolRegistry(specs=specs)
    ctx = _ctx(registry=registry)
    args = ToolSearchArgs(query="slack")
    result = await handle_tool_search(ctx, args)
    assert result["status"] == "ok"
    assert result["matches"] >= 1
    names = [r["name"] for r in result["results"]]
    assert "slack_send" in names


@pytest.mark.asyncio
async def test_handle_tool_search_excludes_eager_by_default() -> None:
    eager = _spec("eager_send", "send something quickly")
    deferred = _spec("deferred_send", "send a queued message", defer_loading=True)
    registry = ToolRegistry(specs=[eager, deferred])
    ctx = _ctx(registry=registry)
    args = ToolSearchArgs(query="send")
    result = await handle_tool_search(ctx, args)
    assert result["status"] == "ok"
    names = [r["name"] for r in result["results"]]
    assert "deferred_send" in names
    assert "eager_send" not in names


@pytest.mark.asyncio
async def test_handle_tool_search_include_eager_returns_eager_too() -> None:
    eager = _spec("eager_send", "send something quickly")
    deferred = _spec("deferred_send", "send a queued message", defer_loading=True)
    registry = ToolRegistry(specs=[eager, deferred])
    ctx = _ctx(registry=registry)
    args = ToolSearchArgs(query="send", include_eager=True)
    result = await handle_tool_search(ctx, args)
    names = {r["name"] for r in result["results"]}
    assert names == {"eager_send", "deferred_send"}


@pytest.mark.asyncio
async def test_handle_tool_search_returns_empty_on_no_match() -> None:
    specs = [_spec("slack_send", "send a Slack message", defer_loading=True)]
    registry = ToolRegistry(specs=specs)
    ctx = _ctx(registry=registry)
    args = ToolSearchArgs(query="completely-unrelated-XYZQRS")
    result = await handle_tool_search(ctx, args)
    assert result["status"] == "ok"
    assert result["matches"] == 0
    assert result["results"] == []


# ── ToolSearchArgs validation ──────────────────────────────────────────


def test_args_query_empty_string_rejected() -> None:
    with pytest.raises(ValueError):
        ToolSearchArgs(query="")


def test_args_top_k_zero_rejected() -> None:
    with pytest.raises(ValueError):
        ToolSearchArgs(query="x", top_k=0)


def test_args_top_k_too_large_rejected() -> None:
    with pytest.raises(ValueError):
        ToolSearchArgs(query="x", top_k=21)


def test_args_top_k_default_is_five() -> None:
    args = ToolSearchArgs(query="x")
    assert args.top_k == 5
    assert args.include_eager is False


# ── Default registry integration ───────────────────────────────────────


def test_tool_search_registered_in_default_registry() -> None:
    registry = build_default_registry()
    assert "tool_search" in registry.names()
    spec = registry.get("tool_search")
    assert spec is not None
    assert spec.defer_loading is False  # tool_search itself is eager


@pytest.mark.asyncio
async def test_invoke_tool_search_through_registry() -> None:
    """End-to-end: registry.invoke_async routes ``tool_search``."""
    registry = build_default_registry()
    ctx = _ctx(registry=registry)
    call = ToolCall(
        tool="tool_search",
        args={"query": "slack", "top_k": 3},
        order_in_reply=0,
    )
    result = await registry.invoke_async(call, ctx)
    assert result.status == "ok"
    assert result.payload is not None
    assert result.payload["status"] == "ok"
    # Default registry has zero deferred specs today, so matches == 0 —
    # the seam works; Faz 1 fan-out fills the corpus.
    assert result.payload["matches"] == 0


def test_default_registry_has_zero_deferred_today() -> None:
    """Faz 0 ships the SEAM; behaviour stays identical to pre-Faz 0.

    Every existing spec sets ``defer_loading=False`` (default), so the
    eager catalog is exhausted and ``tool_search`` is a no-op until Faz
    1+ flips the flag on tools that don't need to be in the system
    prompt by default.
    """
    registry = build_default_registry()
    assert registry.deferred_names() == []
    # And every existing tool stays in the eager catalog.
    assert set(registry.eager_names()) == set(registry.names())
