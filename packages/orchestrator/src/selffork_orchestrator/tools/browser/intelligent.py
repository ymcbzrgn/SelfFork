"""Browser intelligent tools — stagehand-style act/extract/observe/agent + smart_locator (5).

S-ToolFleet Faz 2. These tools require an LLM for natural-language → DOM
action translation. When ``ctx.vision_runtime`` is not wired they return
``{"status": "unwired"}`` so Self Jr learns the capability is absent
rather than crashing.

Reference: stagehand (MIT) — act/extract/observe/agent 4-method shape.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.browser._internal import (
    _invoke_browser,
    _require_browser_driver,
)

__all__ = [
    "BrowserActArgs",
    "BrowserAgentArgs",
    "BrowserExtractArgs",
    "BrowserObserveArgs",
    "BrowserSmartLocatorArgs",
    "build_browser_intelligent_tools",
]


class BrowserActArgs(ToolArgs):
    instruction: str = Field(min_length=1, max_length=4_096, description="Natural-language action e.g. 'click the Submit button'")  # noqa: E501


class BrowserExtractArgs(ToolArgs):
    extraction_schema: dict[str, str] = Field(
        min_length=1, description="Field name → description for extraction",
    )
    instruction: str | None = Field(default=None, max_length=2_048)


class BrowserObserveArgs(ToolArgs):
    description: str = Field(min_length=1, max_length=2_048, description="Natural-language element description")  # noqa: E501


class BrowserAgentArgs(ToolArgs):
    goal: str = Field(min_length=1, max_length=4_096)
    max_steps: int = Field(default=5, ge=1, le=50)


class BrowserSmartLocatorArgs(ToolArgs):
    description: str = Field(min_length=1, max_length=1_024)


def _vision_unwired() -> dict[str, Any]:
    return {
        "status": "unwired",
        "reason": "no vision_runtime in ToolContext — set up a multimodal runtime",
    }


async def _browser_act(ctx: ToolContext, args: BrowserActArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    vision = ctx.vision_runtime

    async def _run() -> dict[str, Any]:
        if vision is None:
            return _vision_unwired()
        # Strategy: dump DOM + screenshot, ask the vision LLM for an action plan.
        dom = await drv.dump_dom_tree()
        png = await drv.screenshot()
        prompt = (
            f"You are an autonomous browser agent. Goal: {args.instruction!r}. "
            f"DOM (truncated): {json.dumps(dom[:50])}. Respond with the next action."
        )
        decide = getattr(vision, "decide", None)
        if decide is None:
            return _vision_unwired()
        decision = await decide(prompt=prompt, image=png)
        return {"status": "ok", "decision": str(decision)[:4096]}

    return await _invoke_browser(
        ctx, action_type="browser.act", target_uri=None,
        args_summary={"instruction_len": len(args.instruction)},
        coro_factory=_run,
    )


async def _browser_extract(ctx: ToolContext, args: BrowserExtractArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    vision = ctx.vision_runtime

    async def _run() -> dict[str, Any]:
        if vision is None:
            return _vision_unwired()
        html = await drv.get_html()
        decide = getattr(vision, "decide", None)
        if decide is None:
            return _vision_unwired()
        prompt = (
            "Extract these fields from the HTML below. "
            f"Schema: {json.dumps(args.extraction_schema)}. "
            f"Instruction: {args.instruction or 'extract verbatim'}.\n"
            f"HTML (truncated): {html[:8000]}"
        )
        result = await decide(prompt=prompt, image=None)
        return {"status": "ok", "extracted": str(result)[:8192]}

    return await _invoke_browser(
        ctx, action_type="browser.extract", target_uri=None,
        args_summary={"fields": list(args.extraction_schema.keys())},
        coro_factory=_run,
    )


async def _browser_observe(ctx: ToolContext, args: BrowserObserveArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    vision = ctx.vision_runtime

    async def _run() -> dict[str, Any]:
        if vision is None:
            return _vision_unwired()
        dom = await drv.dump_dom_tree()
        png = await drv.screenshot()
        decide = getattr(vision, "decide", None)
        if decide is None:
            return _vision_unwired()
        prompt = (
            f"Identify the element best matching: {args.description!r}. "
            f"Return a JSON describing the candidate (selector/role/text/bbox). "
            f"DOM (truncated): {json.dumps(dom[:50])}"
        )
        result = await decide(prompt=prompt, image=png)
        return {"status": "ok", "candidate": str(result)[:4096]}

    return await _invoke_browser(
        ctx, action_type="browser.observe", target_uri=None,
        args_summary={"description_len": len(args.description)},
        coro_factory=_run,
    )


async def _browser_agent(ctx: ToolContext, args: BrowserAgentArgs) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)
    vision = ctx.vision_runtime

    async def _run() -> dict[str, Any]:
        if vision is None:
            return _vision_unwired()
        # Faz 2 minimal loop: observe → act for max_steps. Goal verification
        # is delegated to the operator's downstream check.
        decide = getattr(vision, "decide", None)
        if decide is None:
            return _vision_unwired()
        steps: list[dict[str, Any]] = []
        for i in range(args.max_steps):
            dom = await drv.dump_dom_tree()
            png = await drv.screenshot()
            prompt = (
                f"Goal: {args.goal!r}. Step {i + 1}/{args.max_steps}. "
                f"Suggest next action or DONE. DOM: {json.dumps(dom[:30])}"
            )
            decision = await decide(prompt=prompt, image=png)
            text = str(decision)
            steps.append({"step": i + 1, "decision": text[:1024]})
            if "DONE" in text.upper()[:64]:
                return {"status": "ok", "done": True, "steps": steps}
        return {"status": "ok", "done": False, "steps": steps}

    return await _invoke_browser(
        ctx, action_type="browser.agent", target_uri=None,
        args_summary={"goal_len": len(args.goal), "max_steps": args.max_steps},
        coro_factory=_run,
    )


async def _browser_smart_locator(
    ctx: ToolContext, args: BrowserSmartLocatorArgs,
) -> dict[str, Any]:
    drv = _require_browser_driver(ctx)

    async def _find() -> dict[str, Any]:
        # No-LLM fallback: scan DOM tree for nodes whose text contains the description
        dom = await drv.dump_dom_tree()
        needle = args.description.lower()
        candidates = [
            node for node in dom
            if isinstance(node, dict) and needle in str(node).lower()
        ][:10]
        return {"count": len(candidates), "candidates": candidates}

    return await _invoke_browser(
        ctx, action_type="browser.smart_locator", target_uri=None,
        args_summary={"description_len": len(args.description)},
        coro_factory=_find,
    )


def build_browser_intelligent_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(name="browser_act",
                 description="Translate a natural-language instruction into a browser action via LLM.",  # noqa: E501
                 args_model=BrowserActArgs, handler=_browser_act, defer_loading=True),
        ToolSpec(name="browser_extract",
                 description="Extract structured data from the active page via schema + LLM.",
                 args_model=BrowserExtractArgs, handler=_browser_extract, defer_loading=True),
        ToolSpec(name="browser_observe",
                 description="Identify the element matching a natural-language description.",
                 args_model=BrowserObserveArgs, handler=_browser_observe, defer_loading=True),
        ToolSpec(name="browser_agent",
                 description="Autonomous observe→act loop towards a goal (max_steps capped).",
                 args_model=BrowserAgentArgs, handler=_browser_agent, defer_loading=True),
        ToolSpec(name="browser_smart_locator",
                 description="Scan DOM for nodes matching a description (no-LLM heuristic fallback).",  # noqa: E501
                 args_model=BrowserSmartLocatorArgs, handler=_browser_smart_locator, defer_loading=True),  # noqa: E501
    ]
