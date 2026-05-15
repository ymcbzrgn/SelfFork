"""SecurityWatchdog — domain allowlist + redirect block + popup block."""

from __future__ import annotations

from selffork_body.drivers.web import SecurityWatchdog


def test_no_allowlist_means_no_restriction() -> None:
    watchdog = SecurityWatchdog()
    assert watchdog.is_allowed("https://anywhere.example/")


def test_exact_domain_match() -> None:
    watchdog = SecurityWatchdog(allowed_domains={"example.com"})
    assert watchdog.is_allowed("https://example.com/path")


def test_subdomain_match() -> None:
    watchdog = SecurityWatchdog(allowed_domains={"example.com"})
    assert watchdog.is_allowed("https://api.example.com/v1")


def test_unrelated_domain_blocked() -> None:
    watchdog = SecurityWatchdog(allowed_domains={"example.com"})
    assert not watchdog.is_allowed("https://attacker.com")


def test_userinfo_stripped_before_comparison() -> None:
    watchdog = SecurityWatchdog(allowed_domains={"example.com"})
    assert watchdog.is_allowed("https://attacker@example.com")


def test_port_stripped_before_comparison() -> None:
    watchdog = SecurityWatchdog(allowed_domains={"example.com"})
    assert watchdog.is_allowed("https://example.com:8443")


def test_idn_normalised() -> None:
    watchdog = SecurityWatchdog(allowed_domains={"münchen.de"})
    assert watchdog.is_allowed("https://münchen.de/path")


def test_lookalike_subdomain_not_matched() -> None:
    watchdog = SecurityWatchdog(allowed_domains={"example.com"})
    assert not watchdog.is_allowed("https://example.com.attacker.tld")


async def test_on_framenavigated_blocks_disallowed_url() -> None:
    block_log: list[tuple[str, str]] = []

    class _StubFrame:
        def __init__(self, url: str) -> None:
            self.url = url
            self.evaluate_calls: list[str] = []

        async def evaluate(self, script: str) -> None:
            self.evaluate_calls.append(script)

    watchdog = SecurityWatchdog(
        allowed_domains={"example.com"},
        on_block=lambda kind, url: block_log.append((kind, url)),
    )
    frame = _StubFrame("https://attacker.com")
    await watchdog.on_framenavigated(frame)
    assert watchdog.blocked_count == 1
    assert block_log == [("framenavigated", "https://attacker.com")]
    assert "about:blank" in frame.evaluate_calls[0]


async def test_on_popup_closes_disallowed_popup() -> None:
    closed: list[bool] = []

    class _StubPopup:
        def __init__(self, url: str) -> None:
            self.url = url

        async def close(self) -> None:
            closed.append(True)

    watchdog = SecurityWatchdog(allowed_domains={"example.com"})
    await watchdog.on_popup(_StubPopup("https://attacker.com"))
    assert watchdog.blocked_count == 1
    assert closed == [True]


async def test_on_framenavigated_ignores_about_blank() -> None:
    class _StubFrame:
        url = "about:blank"

        async def evaluate(self, _script):
            raise AssertionError("should not be called")

    watchdog = SecurityWatchdog(allowed_domains={"example.com"})
    await watchdog.on_framenavigated(_StubFrame())
    assert watchdog.blocked_count == 0
