"""Android intent tools — intent / broadcast / deeplink / press_button / notification (5)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from selffork_orchestrator.tools.base import ToolArgs, ToolContext, ToolSpec
from selffork_orchestrator.tools.mobile._internal import (
    _invoke_mobile,
    _require_android_driver,
)

__all__ = [
    "AndroidBroadcastArgs",
    "AndroidDeeplinkArgs",
    "AndroidIntentArgs",
    "AndroidNotificationPostArgs",
    "AndroidPressButtonArgs",
    "build_android_intent_tools",
]


class AndroidIntentArgs(ToolArgs):
    action: str = Field(min_length=1, max_length=256)
    component: str | None = Field(default=None, max_length=512)
    data: str | None = Field(default=None, max_length=4096)
    extras: dict[str, str] | None = Field(default=None)


class AndroidBroadcastArgs(ToolArgs):
    action: str = Field(min_length=1, max_length=256)
    extras: dict[str, str] | None = Field(default=None)


class AndroidDeeplinkArgs(ToolArgs):
    url: str = Field(min_length=1, max_length=4096)


class AndroidPressButtonArgs(ToolArgs):
    button: Literal[
        "back",
        "home",
        "menu",
        "app_switch",
        "recent",
        "power",
        "lock",
        "volume_up",
        "volume_down",
    ] = Field(description="Hardware/system button name")


class AndroidNotificationPostArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=1024)
    package: str | None = Field(default=None)


async def _android_intent(ctx: ToolContext, args: AndroidIntentArgs) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _send() -> dict[str, Any]:
        text = await drv.intent(
            args.action,
            extras=args.extras,
            component=args.component,
            data=args.data,
        )
        return {"output": text[:4096]}

    return await _invoke_mobile(
        ctx,
        action_type="android.intent",
        target_uri=args.component or args.action,
        args_summary={
            "action": args.action,
            "component": args.component,
            "data": args.data,
            "extras_count": len(args.extras or {}),
        },
        coro_factory=_send,
    )


async def _android_broadcast(
    ctx: ToolContext,
    args: AndroidBroadcastArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _send() -> dict[str, Any]:
        text = await drv.broadcast(args.action, extras=args.extras)
        return {"output": text[:4096]}

    return await _invoke_mobile(
        ctx,
        action_type="android.broadcast",
        target_uri=args.action,
        args_summary={
            "action": args.action,
            "extras_count": len(args.extras or {}),
        },
        coro_factory=_send,
    )


async def _android_deeplink(
    ctx: ToolContext,
    args: AndroidDeeplinkArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)

    async def _open() -> dict[str, Any]:
        text = await drv.deeplink(args.url)
        return {"output": text[:2048]}

    return await _invoke_mobile(
        ctx,
        action_type="android.deeplink",
        target_uri=args.url,
        args_summary={"url": args.url},
        coro_factory=_open,
    )


async def _android_press_button(
    ctx: ToolContext,
    args: AndroidPressButtonArgs,
) -> dict[str, Any]:
    drv = _require_android_driver(ctx)
    return await _invoke_mobile(
        ctx,
        action_type="android.press_button",
        target_uri=None,
        args_summary={"button": args.button},
        coro_factory=lambda: drv.press_button(args.button),
    )


async def _android_notification_post(
    ctx: ToolContext,
    args: AndroidNotificationPostArgs,
) -> dict[str, Any]:
    """Post a system notification via a synthetic intent.

    Uses ``am start`` to fire a NotificationCompat-like intent; falls
    back to a shell ``cmd notification post`` when available. Result
    text returned for caller introspection.
    """
    drv = _require_android_driver(ctx)

    async def _post() -> dict[str, Any]:
        cmd = f"cmd notification post -S bigtext -t {args.title!r} selffork-toolfleet {args.body!r}"
        out = await drv.shell(cmd)
        return {"output": out[:1024], "package": args.package}

    return await _invoke_mobile(
        ctx,
        action_type="android.notification_post",
        target_uri=None,
        args_summary={
            "title_len": len(args.title),
            "body_len": len(args.body),
            "package": args.package,
        },
        coro_factory=_post,
    )


def build_android_intent_tools() -> list[ToolSpec[Any]]:
    return [
        ToolSpec(
            name="android_intent",
            description=(
                "Fire an Android Intent (am start) with optional component, "
                "data URI and string extras."
            ),
            args_model=AndroidIntentArgs,
            handler=_android_intent,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_broadcast",
            description="Send an Android broadcast intent (am broadcast).",
            args_model=AndroidBroadcastArgs,
            handler=_android_broadcast,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_deeplink",
            description="Open a URL on Android (am start VIEW).",
            args_model=AndroidDeeplinkArgs,
            handler=_android_deeplink,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_press_button",
            description="Press an Android hardware button (alias for press_key).",
            args_model=AndroidPressButtonArgs,
            handler=_android_press_button,
            defer_loading=True,
        ),
        ToolSpec(
            name="android_notification_post",
            description="Post a system notification (cmd notification post).",
            args_model=AndroidNotificationPostArgs,
            handler=_android_notification_post,
            defer_loading=True,
        ),
    ]
