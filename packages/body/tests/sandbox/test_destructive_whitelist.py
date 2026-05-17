"""Tests for the destructive-action whitelist + matcher (ADR-006 §4.5)."""

from __future__ import annotations

from selffork_body.sandbox.destructive_whitelist import (
    CandidateAction,
    DestructiveWhitelist,
)


def _default_whitelist() -> DestructiveWhitelist:
    """Load the shipped default whitelist (data/destructive_actions.yaml)."""
    return DestructiveWhitelist.load()


def test_default_whitelist_loads_seven_categories() -> None:
    wl = _default_whitelist()
    ids = {c.id for c in wl.categories}
    assert ids == {
        "prod_deploy",
        "db_destructive",
        "force_push",
        "file_destructive",
        "account_destructive",
        "financial",
        "social_outbound",
    }


def test_match_git_push_origin_main() -> None:
    wl = _default_whitelist()
    action = CandidateAction(tool="git", args=("push", "origin", "main"))
    cat = wl.match(action)
    assert cat is not None
    assert cat.id == "prod_deploy"
    assert cat.confirm_window_hours == 4


def test_match_git_force_push() -> None:
    wl = _default_whitelist()
    action = CandidateAction(tool="git", args=("push", "--force"))
    cat = wl.match(action)
    assert cat is not None
    assert cat.id == "force_push"


def test_match_rm_rf() -> None:
    wl = _default_whitelist()
    action = CandidateAction(tool="rm", args=("-rf", "/opt/data"))
    cat = wl.match(action)
    assert cat is not None
    assert cat.id == "file_destructive"


def test_match_drop_table_sql() -> None:
    wl = _default_whitelist()
    action = CandidateAction(sql="DROP TABLE users CASCADE;")
    cat = wl.match(action)
    assert cat is not None
    assert cat.id == "db_destructive"


def test_match_stripe_url() -> None:
    wl = _default_whitelist()
    action = CandidateAction(
        url="https://checkout.stripe.com/sessions/abc123",
        http_method="POST",
    )
    cat = wl.match(action)
    assert cat is not None
    assert cat.id == "financial"


def test_match_social_outbound_has_one_hour_window() -> None:
    wl = _default_whitelist()
    action = CandidateAction(url="https://twitter.com/intent/tweet?text=hi")
    cat = wl.match(action)
    assert cat is not None
    assert cat.id == "social_outbound"
    assert cat.confirm_window_hours == 1


def test_safe_action_does_not_match() -> None:
    wl = _default_whitelist()
    safe_actions = [
        CandidateAction(tool="git", args=("status",)),
        CandidateAction(tool="git", args=("log", "--oneline")),
        CandidateAction(tool="ls", args=("-la",)),
        CandidateAction(tool="npm", args=("test",)),
        CandidateAction(sql="SELECT * FROM users LIMIT 10"),
        CandidateAction(url="https://api.github.com/repos", http_method="GET"),
    ]
    for action in safe_actions:
        assert wl.match(action) is None, f"unexpected match for {action}"


def test_word_boundary_avoids_substring_false_positive() -> None:
    """`args_contains=['main']` should not match `args=['domain']`."""
    wl = _default_whitelist()
    action = CandidateAction(
        tool="git", args=("push", "origin", "domain-feature")
    )
    cat = wl.match(action)
    # prod_deploy needs all of push/origin/main; "domain-feature" is
    # not "main", so prod_deploy must not fire.
    assert cat is None or cat.id != "prod_deploy"


def test_from_raw_parses_custom_yaml_dict() -> None:
    custom = {
        "destructive_actions": [
            {
                "id": "custom",
                "description": "operator-specific destructive",
                "confirm_window_hours": 2,
                "match_any": [
                    {"tool": "kubectl", "args_contains": ["delete", "namespace"]},
                ],
            }
        ]
    }
    wl = DestructiveWhitelist.from_raw(custom)
    assert len(wl.categories) == 1
    cat = wl.match(
        CandidateAction(tool="kubectl", args=("delete", "namespace", "prod"))
    )
    assert cat is not None
    assert cat.id == "custom"
    assert cat.confirm_window_hours == 2


def test_empty_rule_does_not_match_anything() -> None:
    """A rule with no constraints set should NOT be a catch-all."""
    custom = {
        "destructive_actions": [
            {
                "id": "noop",
                "description": "no constraints",
                "confirm_window_hours": 4,
                "match_any": [{}],
            }
        ]
    }
    wl = DestructiveWhitelist.from_raw(custom)
    assert (
        wl.match(CandidateAction(tool="anything", args=("foo",))) is None
    )
