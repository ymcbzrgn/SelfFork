"""Background expiry sweep for :class:`PendingConfirmationStore`.

The store can only flip a stale entry to ``expired`` when *someone*
calls :meth:`expire_stale`. The destructive guard does this every poll
inside the round-loop, but the dashboard server also needs an
ambient sweeper so:

1. Entries whose run process exited (e.g. operator cancelled the
   session before approving) still flip to ``expired`` on their own
   timer, producing the fail-safe-NO Telegram notification.
2. The topbar pending count never shows a window that is already
   logically dead.

The loop is intentionally trivial: poll every ``interval`` seconds,
call ``store.expire_stale()``, log if anything flipped, sleep again.
Cancellable via :class:`asyncio.Task.cancel`.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Final

from selffork_body.sandbox.pending_confirmations import PendingConfirmationStore
from selffork_shared.logging import get_logger

__all__ = [
    "DEFAULT_EXPIRE_INTERVAL_SECONDS",
    "expire_loop",
]

_log = get_logger(__name__)

DEFAULT_EXPIRE_INTERVAL_SECONDS: Final[float] = 60.0


async def expire_loop(
    *,
    store: PendingConfirmationStore,
    interval_seconds: float = DEFAULT_EXPIRE_INTERVAL_SECONDS,
) -> None:
    """Run forever (until cancelled) sweeping expired pending entries.

    Args:
        store: The shared pending-confirmation store. The same instance
            the warden writes into and the dashboard router serves.
        interval_seconds: Sweep cadence. 60s is the published default —
            destructive windows are measured in hours, so the latency
            between an actual timeout and the ``expired`` flip is
            bounded by this value (acceptable).
    """
    if interval_seconds <= 0:
        msg = "interval_seconds must be positive"
        raise ValueError(msg)
    try:
        while True:
            try:
                flipped = store.expire_stale()
            except Exception:  # pragma: no cover — defensive log only
                _log.exception("destructive_expire_sweep_failed")
                flipped = []
            if flipped:
                _log.info(
                    "destructive_expire_sweep",
                    flipped=len(flipped),
                    ids=[e.id for e in flipped],
                )
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        # Final sweep on shutdown so an in-flight expiry is captured
        # before the loop tears down.
        with contextlib.suppress(Exception):
            store.expire_stale()
        raise
