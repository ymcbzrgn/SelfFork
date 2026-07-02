"""The intelligent browser tools go live once ``vision_runtime`` is wired.

Guards the W3 contract end-to-end: the tool result envelope is
``{"status": "ok", "result": {...}}`` (from the body ``_invoke`` wrapper), so
the meaningful tool status lives at ``result["result"]["status"]``. With a
runtime exposing ``decide(prompt, image)`` the inner status is ``ok`` and the
runtime is actually called; without one it stays ``unwired``.
"""

from __future__ import annotations

from selffork_orchestrator.tools.browser.intelligent import (
    BrowserActArgs,
    BrowserExtractArgs,
    _browser_act,
    _browser_extract,
)


async def test_browser_act_live_with_vision(ctx_browser_vision, stub_vision_runtime) -> None:
    result = await _browser_act(
        ctx_browser_vision, BrowserActArgs(instruction="click the Submit button")
    )
    inner = result["result"]
    assert inner["status"] == "ok"
    assert "VISION_OK" in inner["decision"]
    # The runtime was really invoked (not a trivially-passing envelope).
    assert stub_vision_runtime.calls


async def test_browser_extract_live_with_vision(ctx_browser_vision, stub_vision_runtime) -> None:
    result = await _browser_extract(
        ctx_browser_vision,
        BrowserExtractArgs(extraction_schema={"title": "the page title"}),
    )
    inner = result["result"]
    assert inner["status"] == "ok"
    assert "VISION_OK" in inner["extracted"]
    # extract is the text-only path — the consumer passes image=None.
    prompt, image = stub_vision_runtime.calls[0]
    assert image is None


async def test_browser_act_unwired_without_vision(ctx_browser) -> None:
    result = await _browser_act(
        ctx_browser, BrowserActArgs(instruction="click the Submit button")
    )
    assert result["result"]["status"] == "unwired"
