"""End-to-end handler dispatch — every browser tool reaches the stub driver."""

from __future__ import annotations

import pytest

from selffork_orchestrator.tools.base import _UnauthorizedError
from selffork_orchestrator.tools.browser._internal import _require_browser_driver

# Cloak
from selffork_orchestrator.tools.browser.cloak import (
    BrowserClearCacheArgs,
    BrowserEnableStealthArgs,
    BrowserSetExtraHeadersArgs,
    BrowserSetProxyArgs,
    BrowserSetUserAgentArgs,
    _browser_clear_cache,
    _browser_enable_stealth,
    _browser_set_extra_headers,
    _browser_set_proxy,
    _browser_set_user_agent,
)

# Device
from selffork_orchestrator.tools.browser.device import (
    BrowserEmulateDeviceArgs,
    BrowserSetColorSchemeArgs,
    BrowserSetGeolocationArgs,
    BrowserSetLocaleArgs,
    BrowserSetTimezoneArgs,
    _browser_emulate_device,
    _browser_set_color_scheme,
    _browser_set_geolocation,
    _browser_set_locale,
    _browser_set_timezone,
)

# Intelligent
from selffork_orchestrator.tools.browser.intelligent import (
    BrowserActArgs,
    BrowserAgentArgs,
    BrowserExtractArgs,
    BrowserObserveArgs,
    BrowserSmartLocatorArgs,
    _browser_act,
    _browser_agent,
    _browser_extract,
    _browser_observe,
    _browser_smart_locator,
)

# Interaction
from selffork_orchestrator.tools.browser.interaction import (
    BrowserCheckArgs,
    BrowserClickArgs,
    BrowserDoubleClickArgs,
    BrowserDragAndDropArgs,
    BrowserFillFormArgs,
    BrowserHoverArgs,
    BrowserPressKeyArgs,
    BrowserSelectOptionArgs,
    BrowserTypeArgs,
    BrowserUncheckArgs,
    BrowserUploadFileArgs,
    _browser_check,
    _browser_click,
    _browser_double_click,
    _browser_drag_and_drop,
    _browser_fill_form,
    _browser_hover,
    _browser_press_key,
    _browser_select_option,
    _browser_type,
    _browser_uncheck,
    _browser_upload_file,
)

# Navigation
from selffork_orchestrator.tools.browser.navigation import (
    BrowserBackArgs,
    BrowserForwardArgs,
    BrowserGetTitleArgs,
    BrowserGetUrlArgs,
    BrowserNavigateArgs,
    BrowserReloadArgs,
    BrowserSetViewportArgs,
    BrowserWaitForLoadStateArgs,
    BrowserWaitForUrlArgs,
    _browser_back,
    _browser_forward,
    _browser_get_title,
    _browser_get_url,
    _browser_navigate,
    _browser_reload,
    _browser_set_viewport,
    _browser_wait_for_load_state,
    _browser_wait_for_url,
)

# Network
from selffork_orchestrator.tools.browser.network import (
    BrowserBlockUrlPatternArgs,
    BrowserGetNetworkLogArgs,
    BrowserInterceptRequestArgs,
    BrowserMockResponseArgs,
    BrowserWaitForResponseArgs,
    _browser_block_url_pattern,
    _browser_get_network_log,
    _browser_intercept_request,
    _browser_mock_response,
    _browser_wait_for_response,
)

# Observation
from selffork_orchestrator.tools.browser.observation import (
    BrowserDomSnapshotArgs,
    BrowserEvaluateArgs,
    BrowserGetAttributeArgs,
    BrowserGetConsoleLogsArgs,
    BrowserGetHtmlArgs,
    BrowserGetPdfArgs,
    BrowserQuerySelectorAllArgs,
    BrowserQuerySelectorArgs,
    BrowserScreenshotArgs,
    BrowserScreenshotElementArgs,
    BrowserTextContentArgs,
    _browser_dom_snapshot,
    _browser_evaluate,
    _browser_get_attribute,
    _browser_get_console_logs,
    _browser_get_html,
    _browser_get_pdf,
    _browser_query_selector,
    _browser_query_selector_all,
    _browser_screenshot,
    _browser_screenshot_element,
    _browser_text_content,
)

# Storage
from selffork_orchestrator.tools.browser.storage import (
    BrowserCookiesClearArgs,
    BrowserCookiesGetArgs,
    BrowserCookiesSetArgs,
    BrowserLocalStorageClearArgs,
    BrowserLocalStorageGetArgs,
    BrowserLocalStorageSetArgs,
    _browser_cookies_clear,
    _browser_cookies_get,
    _browser_cookies_set,
    _browser_local_storage_clear,
    _browser_local_storage_get,
    _browser_local_storage_set,
)

# Tabs
from selffork_orchestrator.tools.browser.tabs import (
    BrowserCloseTabArgs,
    BrowserDuplicateTabArgs,
    BrowserGetActiveTabArgs,
    BrowserListTabsArgs,
    BrowserNewTabArgs,
    BrowserSwitchTabArgs,
    _browser_close_tab,
    _browser_duplicate_tab,
    _browser_get_active_tab,
    _browser_list_tabs,
    _browser_new_tab,
    _browser_switch_tab,
)

# ---- gate -----------------------------------------------------------------


async def test_require_browser_driver_returns_driver(ctx_browser, stub_browser_driver) -> None:
    drv = _require_browser_driver(ctx_browser)
    assert drv is stub_browser_driver


async def test_require_browser_driver_unauthorized_when_no_driver(ctx_no_browser) -> None:
    with pytest.raises(_UnauthorizedError):
        _require_browser_driver(ctx_no_browser)


# ---- Interaction (11) ---------------------------------------------------


async def test_browser_click_selector(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_click(ctx_browser, BrowserClickArgs(target="#submit"))
    assert result["status"] == "ok"
    assert any(c[0] == "click" for c in stub_browser_driver.calls)


async def test_browser_click_coords(ctx_browser, stub_browser_driver) -> None:
    await _browser_click(ctx_browser, BrowserClickArgs(x=10, y=20))
    assert any(c[0] == "click" for c in stub_browser_driver.calls)


async def test_browser_double_click(ctx_browser, stub_browser_driver) -> None:
    await _browser_double_click(ctx_browser, BrowserDoubleClickArgs(target="#x"))
    assert any(c[0] == "double_click" for c in stub_browser_driver.calls)


async def test_browser_type(ctx_browser, stub_browser_driver) -> None:
    await _browser_type(ctx_browser, BrowserTypeArgs(text="hello"))
    assert any(c[0] == "type_text" for c in stub_browser_driver.calls)


async def test_browser_type_clear_first(ctx_browser, stub_browser_driver) -> None:
    await _browser_type(ctx_browser, BrowserTypeArgs(text="x", target="#f", clear_first=True))
    names = [c[0] for c in stub_browser_driver.calls]
    assert names.index("clear") < names.index("type_text")


async def test_browser_fill_form(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_fill_form(
        ctx_browser, BrowserFillFormArgs(fields={"#a": "1", "#b": "2"}),
    )
    assert result["result"]["filled"] == 2


async def test_browser_hover(ctx_browser, stub_browser_driver) -> None:
    await _browser_hover(ctx_browser, BrowserHoverArgs(target="#x"))
    assert any(c[0] == "hover" for c in stub_browser_driver.calls)


async def test_browser_press_key(ctx_browser, stub_browser_driver) -> None:
    await _browser_press_key(ctx_browser, BrowserPressKeyArgs(key="Enter"))
    assert ("press_key", ("Enter",), {}) in stub_browser_driver.calls


async def test_browser_select_option(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_select_option(
        ctx_browser, BrowserSelectOptionArgs(target="#s", value="x"),
    )
    assert result["result"]["selected"] == ["x"]


async def test_browser_check(ctx_browser, stub_browser_driver) -> None:
    await _browser_check(ctx_browser, BrowserCheckArgs(target="#cb"))
    assert ("check", ("#cb",), {}) in stub_browser_driver.calls


async def test_browser_uncheck(ctx_browser, stub_browser_driver) -> None:
    await _browser_uncheck(ctx_browser, BrowserUncheckArgs(target="#cb"))
    assert ("uncheck", ("#cb",), {}) in stub_browser_driver.calls


async def test_browser_drag_and_drop(ctx_browser, stub_browser_driver) -> None:
    await _browser_drag_and_drop(
        ctx_browser, BrowserDragAndDropArgs(source="#a", target="#b"),
    )
    assert ("drag_and_drop", ("#a", "#b"), {}) in stub_browser_driver.calls


async def test_browser_upload_file(ctx_browser, stub_browser_driver) -> None:
    await _browser_upload_file(
        ctx_browser,
        BrowserUploadFileArgs(target="#up", file_path="/tmp/x.txt"),
    )
    assert any(c[0] == "upload_file" for c in stub_browser_driver.calls)


# ---- Navigation (9) ------------------------------------------------------


async def test_browser_navigate(ctx_browser, stub_browser_driver) -> None:
    await _browser_navigate(ctx_browser, BrowserNavigateArgs(url="https://x"))
    assert ("goto", ("https://x",), {}) in stub_browser_driver.calls


async def test_browser_back(ctx_browser, stub_browser_driver) -> None:
    await _browser_back(ctx_browser, BrowserBackArgs())
    assert ("back", (), {}) in stub_browser_driver.calls


async def test_browser_forward(ctx_browser, stub_browser_driver) -> None:
    await _browser_forward(ctx_browser, BrowserForwardArgs())
    assert ("forward", (), {}) in stub_browser_driver.calls


async def test_browser_reload(ctx_browser, stub_browser_driver) -> None:
    await _browser_reload(ctx_browser, BrowserReloadArgs())
    assert ("reload", (), {}) in stub_browser_driver.calls


async def test_browser_get_url(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_get_url(ctx_browser, BrowserGetUrlArgs())
    assert result["result"]["url"] == "https://selffork.dev"


async def test_browser_get_title(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_get_title(ctx_browser, BrowserGetTitleArgs())
    assert result["result"]["title"] == "SelfFork"


async def test_browser_set_viewport(ctx_browser, stub_browser_driver) -> None:
    await _browser_set_viewport(ctx_browser, BrowserSetViewportArgs(width=1024, height=768))
    assert ("set_viewport", (1024, 768), {}) in stub_browser_driver.calls


async def test_browser_wait_for_load_state(ctx_browser, stub_browser_driver) -> None:
    await _browser_wait_for_load_state(
        ctx_browser, BrowserWaitForLoadStateArgs(state="networkidle"),
    )
    assert any(c[0] == "wait_for_load_state" for c in stub_browser_driver.calls)


async def test_browser_wait_for_url(ctx_browser, stub_browser_driver) -> None:
    await _browser_wait_for_url(
        ctx_browser, BrowserWaitForUrlArgs(url_pattern="https://x*"),
    )
    assert any(c[0] == "wait_for_url" for c in stub_browser_driver.calls)


# ---- Observation (11) ----------------------------------------------------


async def test_browser_screenshot(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_screenshot(ctx_browser, BrowserScreenshotArgs())
    assert result["result"]["bytes_size"] > 0


async def test_browser_dom_snapshot(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_dom_snapshot(ctx_browser, BrowserDomSnapshotArgs())
    assert result["result"]["node_count"] == 3


async def test_browser_text_content(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_text_content(
        ctx_browser, BrowserTextContentArgs(target="#x"),
    )
    assert result["result"]["text"] == "Hello"


async def test_browser_get_attribute(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_get_attribute(
        ctx_browser, BrowserGetAttributeArgs(target="#x", name="href"),
    )
    assert result["result"]["value"] == "attr_value"


async def test_browser_evaluate(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_evaluate(
        ctx_browser, BrowserEvaluateArgs(js_code="1+1"),
    )
    assert "result" in result["result"]


async def test_browser_query_selector(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_query_selector(
        ctx_browser, BrowserQuerySelectorArgs(target="#x"),
    )
    assert result["result"]["found"] is True


async def test_browser_query_selector_all(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_query_selector_all(
        ctx_browser, BrowserQuerySelectorAllArgs(target="div"),
    )
    assert result["result"]["count"] == 1


async def test_browser_get_pdf(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_get_pdf(ctx_browser, BrowserGetPdfArgs())
    assert result["result"]["bytes_size"] > 0


async def test_browser_screenshot_element(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_screenshot_element(
        ctx_browser, BrowserScreenshotElementArgs(target="#x"),
    )
    assert result["result"]["bytes_size"] > 0


async def test_browser_get_html(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_get_html(ctx_browser, BrowserGetHtmlArgs())
    assert "SelfFork" in result["result"]["preview"]


async def test_browser_get_console_logs(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_get_console_logs(
        ctx_browser, BrowserGetConsoleLogsArgs(),
    )
    assert result["result"]["count"] == 1


# ---- Tabs (6) ------------------------------------------------------------


async def test_browser_new_tab(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_new_tab(ctx_browser, BrowserNewTabArgs(url="https://x"))
    assert result["result"]["index"] == 1


async def test_browser_close_tab(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_close_tab(ctx_browser, BrowserCloseTabArgs())
    assert result["result"]["remaining"] == 0


async def test_browser_list_tabs(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_list_tabs(ctx_browser, BrowserListTabsArgs())
    assert result["result"]["count"] == 1


async def test_browser_switch_tab(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_switch_tab(ctx_browser, BrowserSwitchTabArgs(index=0))
    assert result["result"]["index"] == "0"


async def test_browser_get_active_tab(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_get_active_tab(ctx_browser, BrowserGetActiveTabArgs())
    assert result["result"]["index"] == "0"


async def test_browser_duplicate_tab(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_duplicate_tab(ctx_browser, BrowserDuplicateTabArgs())
    assert result["result"]["index"] == 1


# ---- Storage (6) ---------------------------------------------------------


async def test_browser_cookies_get(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_cookies_get(ctx_browser, BrowserCookiesGetArgs())
    assert result["result"]["count"] == 1


async def test_browser_cookies_set(ctx_browser, stub_browser_driver) -> None:
    await _browser_cookies_set(
        ctx_browser, BrowserCookiesSetArgs(cookies=[{"name": "x", "value": "1"}]),
    )
    assert any(c[0] == "cookies_set" for c in stub_browser_driver.calls)


async def test_browser_cookies_clear(ctx_browser, stub_browser_driver) -> None:
    await _browser_cookies_clear(ctx_browser, BrowserCookiesClearArgs())
    assert ("cookies_clear", (), {}) in stub_browser_driver.calls


async def test_browser_local_storage_get(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_local_storage_get(
        ctx_browser, BrowserLocalStorageGetArgs(key="x"),
    )
    assert result["result"]["value"] == "stored"


async def test_browser_local_storage_set(ctx_browser, stub_browser_driver) -> None:
    await _browser_local_storage_set(
        ctx_browser, BrowserLocalStorageSetArgs(key="x", value="v"),
    )
    assert any(c[0] == "local_storage_set" for c in stub_browser_driver.calls)


async def test_browser_local_storage_clear(ctx_browser, stub_browser_driver) -> None:
    await _browser_local_storage_clear(
        ctx_browser, BrowserLocalStorageClearArgs(),
    )
    assert ("local_storage_clear", (), {}) in stub_browser_driver.calls


# ---- Cloak (5) -----------------------------------------------------------


async def test_browser_set_user_agent(ctx_browser, stub_browser_driver) -> None:
    await _browser_set_user_agent(
        ctx_browser, BrowserSetUserAgentArgs(user_agent="UA/1"),
    )
    assert ("set_user_agent", ("UA/1",), {}) in stub_browser_driver.calls


async def test_browser_set_extra_headers(ctx_browser, stub_browser_driver) -> None:
    await _browser_set_extra_headers(
        ctx_browser, BrowserSetExtraHeadersArgs(headers={"X": "Y"}),
    )
    assert any(c[0] == "set_extra_headers" for c in stub_browser_driver.calls)


async def test_browser_enable_stealth(ctx_browser, stub_browser_driver) -> None:
    await _browser_enable_stealth(ctx_browser, BrowserEnableStealthArgs())
    assert ("enable_stealth", (), {}) in stub_browser_driver.calls


async def test_browser_set_proxy(ctx_browser, stub_browser_driver) -> None:
    await _browser_set_proxy(
        ctx_browser, BrowserSetProxyArgs(server="http://proxy:8080"),
    )
    assert any(c[0] == "set_proxy" for c in stub_browser_driver.calls)


async def test_browser_clear_cache(ctx_browser, stub_browser_driver) -> None:
    await _browser_clear_cache(ctx_browser, BrowserClearCacheArgs())
    assert ("clear_cache", (), {}) in stub_browser_driver.calls


# ---- Network (5) ---------------------------------------------------------


async def test_browser_intercept_request(ctx_browser, stub_browser_driver) -> None:
    await _browser_intercept_request(
        ctx_browser, BrowserInterceptRequestArgs(url_pattern="**/*"),
    )
    assert any(c[0] == "intercept_request" for c in stub_browser_driver.calls)


async def test_browser_mock_response(ctx_browser, stub_browser_driver) -> None:
    await _browser_mock_response(
        ctx_browser, BrowserMockResponseArgs(url_pattern="**/api/*", body="{}"),
    )
    assert any(c[0] == "mock_response" for c in stub_browser_driver.calls)


async def test_browser_block_url_pattern(ctx_browser, stub_browser_driver) -> None:
    await _browser_block_url_pattern(
        ctx_browser, BrowserBlockUrlPatternArgs(url_pattern="**/ads/*"),
    )
    assert any(c[0] == "block_url_pattern" for c in stub_browser_driver.calls)


async def test_browser_wait_for_response(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_wait_for_response(
        ctx_browser, BrowserWaitForResponseArgs(url_pattern="**/api/*"),
    )
    assert result["result"]["status"] == 200


async def test_browser_get_network_log(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_get_network_log(
        ctx_browser, BrowserGetNetworkLogArgs(),
    )
    assert result["result"]["count"] == 1


# ---- Device (5) ----------------------------------------------------------


async def test_browser_emulate_device(ctx_browser, stub_browser_driver) -> None:
    await _browser_emulate_device(
        ctx_browser, BrowserEmulateDeviceArgs(device_name="iPhone 15"),
    )
    assert ("emulate_device", ("iPhone 15",), {}) in stub_browser_driver.calls


async def test_browser_set_geolocation(ctx_browser, stub_browser_driver) -> None:
    await _browser_set_geolocation(
        ctx_browser, BrowserSetGeolocationArgs(latitude=40.0, longitude=-3.7),
    )
    assert any(c[0] == "set_geolocation" for c in stub_browser_driver.calls)


async def test_browser_set_locale(ctx_browser, stub_browser_driver) -> None:
    await _browser_set_locale(ctx_browser, BrowserSetLocaleArgs(locale="tr-TR"))
    assert ("set_locale", ("tr-TR",), {}) in stub_browser_driver.calls


async def test_browser_set_timezone(ctx_browser, stub_browser_driver) -> None:
    await _browser_set_timezone(
        ctx_browser, BrowserSetTimezoneArgs(timezone_id="Europe/Istanbul"),
    )
    assert ("set_timezone", ("Europe/Istanbul",), {}) in stub_browser_driver.calls


async def test_browser_set_color_scheme(ctx_browser, stub_browser_driver) -> None:
    await _browser_set_color_scheme(
        ctx_browser, BrowserSetColorSchemeArgs(scheme="dark"),
    )
    assert ("set_color_scheme", ("dark",), {}) in stub_browser_driver.calls


# ---- Intelligent (5) — without vision_runtime: "unwired" ----------------


async def test_browser_act_unwired(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_act(ctx_browser, BrowserActArgs(instruction="click submit"))
    assert result["result"]["status"] == "unwired"


async def test_browser_extract_unwired(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_extract(
        ctx_browser, BrowserExtractArgs(extraction_schema={"title": "page title"}),
    )
    assert result["result"]["status"] == "unwired"


async def test_browser_observe_unwired(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_observe(
        ctx_browser, BrowserObserveArgs(description="the login form"),
    )
    assert result["result"]["status"] == "unwired"


async def test_browser_agent_unwired(ctx_browser, stub_browser_driver) -> None:
    result = await _browser_agent(
        ctx_browser, BrowserAgentArgs(goal="navigate to /login", max_steps=2),
    )
    assert result["result"]["status"] == "unwired"


async def test_browser_smart_locator_no_llm(ctx_browser, stub_browser_driver) -> None:
    """smart_locator works without LLM via DOM heuristic."""
    result = await _browser_smart_locator(
        ctx_browser, BrowserSmartLocatorArgs(description="Submit"),
    )
    assert result["result"]["count"] >= 1


async def test_browser_act_with_vision_runtime(stub_browser_driver) -> None:
    """When vision_runtime is wired, act dispatches to it."""
    from selffork_body.sandbox import PermissionWarden, WardenMode
    from selffork_orchestrator.tools.base import ToolContext

    class _StubProjectStore:
        pass

    class _StubVision:
        async def decide(self, *, prompt, image):
            return "ACTION: click #submit"

    ctx = ToolContext(
        session_id="s",
        project_slug=None,
        project_store=_StubProjectStore(),
        body_driver=stub_browser_driver,
        permission_warden=PermissionWarden(mode=WardenMode.DANGER_FULL_ACCESS),
        vision_runtime=_StubVision(),
    )
    result = await _browser_act(ctx, BrowserActArgs(instruction="click submit"))
    assert result["result"]["status"] == "ok"
    assert "ACTION" in result["result"]["decision"]
