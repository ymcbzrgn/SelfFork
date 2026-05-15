"""Unit tests for ``_redact_preview`` — Order 4 / M-7.

The helper is the cockpit Chat tab's last line of defence: every
``tool.result`` audit event carries a ``result_payload_preview`` field
that the UI inlines without further sanitisation. A leak here lands a
credential in the operator's audit JSONL — keep the test bar high.
"""

from __future__ import annotations

import json

from selffork_orchestrator.lifecycle.session import (
    _RESULT_PREVIEW_MAX_CHARS,
    _redact_preview,
)


class TestRedactsSecretsByKey:
    def test_top_level_api_key_redacted(self) -> None:
        out = _redact_preview({"api_key": "sk-abc", "ok": True})
        assert out == {"api_key": "<redacted>", "ok": True}

    def test_token_variants_all_redacted(self) -> None:
        payload = {
            "access_token": "x",
            "refresh_token": "y",
            "BEARER_TOKEN": "z",
            "session_token": "s",
        }
        out = _redact_preview(payload)
        assert out == {
            "access_token": "<redacted>",
            "refresh_token": "<redacted>",
            "BEARER_TOKEN": "<redacted>",
            "session_token": "<redacted>",
        }

    def test_password_credential_secret_redacted(self) -> None:
        out = _redact_preview(
            {"password": "p", "credential_id": "c", "client_secret": "s"},
        )
        assert out == {
            "password": "<redacted>",
            "credential_id": "<redacted>",
            "client_secret": "<redacted>",
        }

    def test_private_key_redacted(self) -> None:
        out = _redact_preview({"private_key": "PEM..."})
        assert out == {"private_key": "<redacted>"}

    def test_authorization_header_redacted(self) -> None:
        out = _redact_preview({"Authorization": "Bearer x"})
        assert out == {"Authorization": "<redacted>"}


class TestRedactsRecursively:
    def test_nested_dict(self) -> None:
        payload = {
            "outer": {
                "inner": {"api_key": "sk-deep"},
                "ok": True,
            },
        }
        out = _redact_preview(payload)
        assert out == {
            "outer": {
                "inner": {"api_key": "<redacted>"},
                "ok": True,
            },
        }

    def test_list_of_dicts(self) -> None:
        payload = {"items": [{"token": "a"}, {"token": "b"}, {"plain": 1}]}
        out = _redact_preview(payload)
        assert out == {
            "items": [
                {"token": "<redacted>"},
                {"token": "<redacted>"},
                {"plain": 1},
            ],
        }

    def test_tuple_normalised_to_list(self) -> None:
        out = _redact_preview({"args": ("safe", {"password": "x"})})
        assert out == {"args": ["safe", {"password": "<redacted>"}]}


class TestPreservesNonSecretValues:
    def test_arbitrary_keys_pass_through(self) -> None:
        payload = {"id": 1, "title": "ok", "tags": ["a", "b"], "n": 3.14}
        out = _redact_preview(payload)
        assert out == payload

    def test_empty_dict_returns_empty(self) -> None:
        assert _redact_preview({}) == {}

    def test_non_dict_value_returns_as_is(self) -> None:
        assert _redact_preview("plain string") == "plain string"
        assert _redact_preview(42) == 42
        assert _redact_preview(None) is None


class TestTruncatesOversize:
    def test_within_budget_passes_through(self) -> None:
        small = {"k": "x" * 100}
        out = _redact_preview(small)
        assert out == small

    def test_oversize_emits_truncation_marker(self) -> None:
        big = {"data": "x" * (_RESULT_PREVIEW_MAX_CHARS + 1_000)}
        out = _redact_preview(big)
        assert isinstance(out, dict)
        assert out["preview_truncated"] is True
        assert out["original_chars"] > _RESULT_PREVIEW_MAX_CHARS
        assert isinstance(out["head"], str)
        assert len(out["head"]) <= _RESULT_PREVIEW_MAX_CHARS

    def test_truncation_still_redacts_first(self) -> None:
        # A massive payload with secrets must still be redacted before
        # truncation — otherwise the head slice could leak.
        big = {
            "api_key": "sk-leak",
            "filler": "x" * (_RESULT_PREVIEW_MAX_CHARS + 1_000),
        }
        out = _redact_preview(big)
        # Either inline (small enough) or truncated marker — in both
        # the api_key value must already be the redacted literal.
        head = out["head"] if isinstance(out, dict) and "head" in out else json.dumps(out)
        assert "sk-leak" not in head
        assert "<redacted>" in head


class TestNeverCrashesOnExoticTypes:
    def test_object_repr_safe_passes_through_as_string(self) -> None:
        # Custom objects with no secret material in their ``__repr__``
        # are rendered to their ``repr()`` — operator sees the value
        # without losing context.
        class Safe:
            def __repr__(self) -> str:
                return "Safe(id=42)"

        out = _redact_preview({"obj": Safe()})
        assert out == {"obj": "Safe(id=42)"}

    def test_object_repr_with_secret_material_is_scrubbed(self) -> None:
        # Post-Order-4 audit fix: a custom object whose ``__repr__``
        # includes a credential lands in the audit log otherwise. The
        # scrubber replaces the whole rendered value with a marker.
        class Leaky:
            def __repr__(self) -> str:
                return "APIClient(api_key='sk-deadbeef')"

        out = _redact_preview({"client": Leaky()})
        assert isinstance(out, dict)
        assert "sk-deadbeef" not in repr(out)
        assert out["client"] == "<redacted-repr>"

    def test_recursion_depth_cap(self) -> None:
        # Deeply nested input must not raise ``RecursionError``; the
        # cap kicks in well before Python's default 1000-frame limit.
        payload: dict[str, object] = {"v": "leaf"}
        for _ in range(64):
            payload = {"k": payload}
        out = _redact_preview(payload)
        # Walk down — at depth 16 we should hit the cap marker.
        cursor: object = out
        depth = 0
        while isinstance(cursor, dict) and "k" in cursor:
            cursor = cursor["k"]
            depth += 1
        assert cursor == "<depth-capped>" or cursor == {"v": "leaf"}
        assert depth <= 17  # cap fires at depth 16


class TestRedactsExtendedSecretPatterns:
    """Order 4 audit follow-up: cookie / client_id / signature / pin /
    otp / nonce / refresh / xsrf / csrf were missing on first pass."""

    def test_cookie_keys_redacted(self) -> None:
        out = _redact_preview(
            {"cookie": "session=abc; auth=jwt", "set-cookie": "x=y"},
        )
        assert out == {
            "cookie": "<redacted>",
            "set-cookie": "<redacted>",
        }

    def test_client_id_redacted(self) -> None:
        out = _redact_preview({"client_id": "abc", "client-id": "xyz"})
        assert out == {
            "client_id": "<redacted>",
            "client-id": "<redacted>",
        }

    def test_signature_and_signed_redacted(self) -> None:
        out = _redact_preview(
            {"signature": "MEUCIQ", "signed_url": "https://..."},
        )
        assert out == {
            "signature": "<redacted>",
            "signed_url": "<redacted>",
        }

    def test_pin_otp_nonce_redacted(self) -> None:
        out = _redact_preview(
            {"pin": "1234", "otp": "888888", "nonce": "abcd"},
        )
        assert out == {
            "pin": "<redacted>",
            "otp": "<redacted>",
            "nonce": "<redacted>",
        }

    def test_csrf_xsrf_x_api_key_redacted(self) -> None:
        out = _redact_preview(
            {
                "csrf_token": "x",
                "xsrf-cookie": "y",
                "x-api-key": "sk-abc",
            },
        )
        assert out == {
            "csrf_token": "<redacted>",
            "xsrf-cookie": "<redacted>",
            "x-api-key": "<redacted>",
        }

    def test_refresh_keys_redacted(self) -> None:
        # ``refresh_token`` already matches via ``token`` substring; this
        # test covers ``refresh_url`` etc. where the operator is not
        # carrying a token but the URL itself is treated as sensitive.
        out = _redact_preview(
            {"refresh_token": "rt-abc", "refresh_url": "https://..."},
        )
        assert out == {
            "refresh_token": "<redacted>",
            "refresh_url": "<redacted>",
        }
