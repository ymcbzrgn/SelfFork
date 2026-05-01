"""Unit tests for :mod:`selffork_orchestrator.projects.slug`."""

from __future__ import annotations

import pytest

from selffork_orchestrator.projects.slug import (
    MAX_SLUG_LEN,
    RESERVED_SLUGS,
    normalize_slug,
    validate_slug,
)
from selffork_shared.errors import ConfigError


class TestNormalizeSlug:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Hello World", "hello-world"),
            ("My-Project", "my-project"),
            ("calc 2.0", "calc-2-0"),
            ("  Spaced  Out  ", "spaced-out"),
            # NFKD ASCII strip handles Turkish characters cleanly.
            ("Yamaç Jr", "yamac-jr"),
            # Dotless ı (U+0131) doesn't NFKD-decompose to ASCII, so it's
            # silently dropped. The slug stays readable + filesystem-safe.
            ("İŞ Ortağı", "is-ortag"),
            # Existing valid slugs are idempotent.
            ("already-a-slug", "already-a-slug"),
            # Mixed punctuation collapses to single dash.
            ("foo!!??bar", "foo-bar"),
            ("foo___bar", "foo-bar"),
        ],
    )
    def test_known_inputs(self, name: str, expected: str) -> None:
        assert normalize_slug(name) == expected

    def test_empty_raises(self) -> None:
        with pytest.raises(ConfigError):
            normalize_slug("")

    def test_only_punctuation_raises(self) -> None:
        with pytest.raises(ConfigError, match="empty slug"):
            normalize_slug("!!!")

    def test_only_unicode_with_no_ascii_drop_raises(self) -> None:
        # Greek alphabet — NFKD doesn't yield ASCII; result is empty.
        with pytest.raises(ConfigError):
            normalize_slug("αβγ")

    def test_long_name_truncates(self) -> None:
        slug = normalize_slug("a" * 200)
        assert len(slug) <= MAX_SLUG_LEN
        # Validator must accept the truncation result.
        validate_slug(slug)


class TestValidateSlug:
    @pytest.mark.parametrize(
        "slug",
        ["a", "abc", "with-dash", "trailing9", "a-b-c-d-1-2"],
    )
    def test_valid(self, slug: str) -> None:
        validate_slug(slug)  # no raise

    @pytest.mark.parametrize(
        "slug",
        ["", "-leading", "trailing-", "with space", "UPPER", "with_under"],
    )
    def test_invalid_shape_raises(self, slug: str) -> None:
        with pytest.raises(ConfigError):
            validate_slug(slug)

    def test_too_long_raises(self) -> None:
        with pytest.raises(ConfigError, match="exceeds"):
            validate_slug("a" * (MAX_SLUG_LEN + 1))

    @pytest.mark.parametrize("reserved", sorted(RESERVED_SLUGS))
    def test_reserved_rejected(self, reserved: str) -> None:
        with pytest.raises(ConfigError, match="reserved"):
            validate_slug(reserved)
