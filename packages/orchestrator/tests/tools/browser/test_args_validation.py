"""Pydantic args validation — parameterised across browser tool families."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from selffork_orchestrator.tools.browser.cloak import (
    BrowserSetExtraHeadersArgs,
    BrowserSetUserAgentArgs,
)
from selffork_orchestrator.tools.browser.device import (
    BrowserEmulateDeviceArgs,
    BrowserSetColorSchemeArgs,
    BrowserSetGeolocationArgs,
    BrowserSetLocaleArgs,
)
from selffork_orchestrator.tools.browser.intelligent import (
    BrowserActArgs,
    BrowserAgentArgs,
    BrowserExtractArgs,
)
from selffork_orchestrator.tools.browser.interaction import (
    BrowserClickArgs,
    BrowserPressKeyArgs,
    BrowserTypeArgs,
)
from selffork_orchestrator.tools.browser.navigation import (
    BrowserNavigateArgs,
    BrowserSetViewportArgs,
    BrowserWaitForLoadStateArgs,
)
from selffork_orchestrator.tools.browser.network import (
    BrowserMockResponseArgs,
)
from selffork_orchestrator.tools.browser.observation import (
    BrowserEvaluateArgs,
    BrowserQuerySelectorAllArgs,
)
from selffork_orchestrator.tools.browser.tabs import BrowserSwitchTabArgs

# ---- Navigation ----------------------------------------------------------


def test_navigate_requires_url() -> None:
    with pytest.raises(ValidationError):
        BrowserNavigateArgs(url="")


def test_set_viewport_bounds() -> None:
    BrowserSetViewportArgs(width=320, height=320)
    BrowserSetViewportArgs(width=10_000, height=10_000)
    with pytest.raises(ValidationError):
        BrowserSetViewportArgs(width=319, height=320)
    with pytest.raises(ValidationError):
        BrowserSetViewportArgs(width=10_001, height=10_001)


def test_wait_for_load_state_enum() -> None:
    BrowserWaitForLoadStateArgs(state="networkidle")
    with pytest.raises(ValidationError):
        BrowserWaitForLoadStateArgs(state="boom")


# ---- Interaction ---------------------------------------------------------


def test_click_accepts_target_or_coords() -> None:
    BrowserClickArgs(target="button#submit")
    BrowserClickArgs(x=10, y=20)


def test_click_button_enum() -> None:
    BrowserClickArgs(target="x", button="right")
    with pytest.raises(ValidationError):
        BrowserClickArgs(target="x", button="middle")


def test_type_text_required() -> None:
    with pytest.raises(ValidationError):
        BrowserTypeArgs(text="")


def test_press_key_required() -> None:
    with pytest.raises(ValidationError):
        BrowserPressKeyArgs(key="")
    BrowserPressKeyArgs(key="Control+a")


# ---- Observation ---------------------------------------------------------


def test_evaluate_required() -> None:
    with pytest.raises(ValidationError):
        BrowserEvaluateArgs(js_code="")


def test_query_selector_all_max_items_bounds() -> None:
    BrowserQuerySelectorAllArgs(target="div", max_items=1)
    BrowserQuerySelectorAllArgs(target="div", max_items=10_000)
    with pytest.raises(ValidationError):
        BrowserQuerySelectorAllArgs(target="div", max_items=0)
    with pytest.raises(ValidationError):
        BrowserQuerySelectorAllArgs(target="div", max_items=10_001)


# ---- Tabs ----------------------------------------------------------------


def test_switch_tab_index_non_negative() -> None:
    BrowserSwitchTabArgs(index=0)
    with pytest.raises(ValidationError):
        BrowserSwitchTabArgs(index=-1)


# ---- Cloak ---------------------------------------------------------------


def test_set_user_agent_required() -> None:
    with pytest.raises(ValidationError):
        BrowserSetUserAgentArgs(user_agent="")


def test_set_extra_headers_non_empty() -> None:
    BrowserSetExtraHeadersArgs(headers={"X-Test": "1"})
    with pytest.raises(ValidationError):
        BrowserSetExtraHeadersArgs(headers={})


# ---- Network -------------------------------------------------------------


def test_mock_response_status_bounds() -> None:
    BrowserMockResponseArgs(url_pattern="**/*", body="{}", status=200)
    BrowserMockResponseArgs(url_pattern="**/*", body="{}", status=599)
    with pytest.raises(ValidationError):
        BrowserMockResponseArgs(url_pattern="**/*", body="{}", status=99)
    with pytest.raises(ValidationError):
        BrowserMockResponseArgs(url_pattern="**/*", body="{}", status=600)


# ---- Device --------------------------------------------------------------


def test_emulate_device_required() -> None:
    with pytest.raises(ValidationError):
        BrowserEmulateDeviceArgs(device_name="")


def test_geolocation_bounds() -> None:
    BrowserSetGeolocationArgs(latitude=0.0, longitude=0.0)
    with pytest.raises(ValidationError):
        BrowserSetGeolocationArgs(latitude=91.0, longitude=0.0)
    with pytest.raises(ValidationError):
        BrowserSetGeolocationArgs(latitude=0.0, longitude=-181.0)


def test_color_scheme_enum() -> None:
    BrowserSetColorSchemeArgs(scheme="dark")
    with pytest.raises(ValidationError):
        BrowserSetColorSchemeArgs(scheme="auto")


def test_locale_min_length() -> None:
    BrowserSetLocaleArgs(locale="en-US")
    with pytest.raises(ValidationError):
        BrowserSetLocaleArgs(locale="x")


# ---- Intelligent ---------------------------------------------------------


def test_act_required() -> None:
    with pytest.raises(ValidationError):
        BrowserActArgs(instruction="")


def test_extract_schema_non_empty() -> None:
    BrowserExtractArgs(extraction_schema={"title": "page title"})
    with pytest.raises(ValidationError):
        BrowserExtractArgs(extraction_schema={})


def test_agent_max_steps_bounds() -> None:
    BrowserAgentArgs(goal="x", max_steps=1)
    BrowserAgentArgs(goal="x", max_steps=50)
    with pytest.raises(ValidationError):
        BrowserAgentArgs(goal="x", max_steps=0)
    with pytest.raises(ValidationError):
        BrowserAgentArgs(goal="x", max_steps=51)
