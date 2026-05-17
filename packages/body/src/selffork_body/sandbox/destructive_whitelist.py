"""Destructive-action whitelist + matcher (ADR-006 §4.5).

A small declarative YAML drives Self Jr's "ask before doing it" list.
Day-to-day work runs full-autonomy; this guard intercepts only the
categories the operator explicitly enumerated (PROD push, DB drop,
force-push, etc.). Match returns a category id; the caller then routes
the action through ``PendingConfirmationStore`` for the 4-hour
fail-safe-NO soft confirmation.

The default whitelist ships in ``data/destructive_actions.yaml``. The
Settings UI (Telegram bridge section) writes back to the same file
when the operator edits categories or per-category window overrides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).parent / "data" / "destructive_actions.yaml"
)


@dataclass(frozen=True)
class MatchRule:
    """One rule inside a category's ``match_any`` list.

    A rule fires when ALL of its specified fields match the candidate
    action; the category fires when ANY of its rules matches.
    """

    tool: str | None = None
    args_contains: tuple[str, ...] = ()
    env_var_set: tuple[str, ...] = ()
    sql_keyword: tuple[str, ...] = ()
    url_contains: tuple[str, ...] = ()
    http_method: str | None = None

    def matches(self, action: "CandidateAction") -> bool:
        # Tool name must equal (case-insensitive) when specified.
        if self.tool is not None:
            if (action.tool or "").lower() != self.tool.lower():
                return False
            if self.args_contains:
                # All tokens must appear (in order, but allowing gaps).
                arg_text = " ".join(action.args)
                if not _all_tokens_present(arg_text, self.args_contains):
                    return False

        if self.env_var_set:
            env_pairs = {f"{k}={v}" for k, v in (action.env or {}).items()}
            if not all(token in env_pairs for token in self.env_var_set):
                return False

        if self.sql_keyword:
            sql_blob = (action.sql or "").upper()
            if not any(kw.upper() in sql_blob for kw in self.sql_keyword):
                return False

        if self.url_contains:
            url = action.url or ""
            if not any(substr in url for substr in self.url_contains):
                return False

        if self.http_method is not None:
            method = (action.http_method or "").upper()
            if method != self.http_method.upper():
                return False

        # If no field of this rule was set, it should NOT fire — that
        # would be a vacuously-true rule (catch-all). Require at least
        # one constraint.
        if not any(
            (
                self.tool,
                self.args_contains,
                self.env_var_set,
                self.sql_keyword,
                self.url_contains,
                self.http_method,
            )
        ):
            return False

        return True


@dataclass(frozen=True)
class DestructiveCategory:
    """One destructive-action category (e.g. ``prod_deploy``)."""

    id: str
    description: str
    confirm_window_hours: int
    match_any: tuple[MatchRule, ...]

    def matches(self, action: "CandidateAction") -> bool:
        return any(rule.matches(action) for rule in self.match_any)


@dataclass(frozen=True)
class CandidateAction:
    """Surface of a potential action for matching.

    Callers fill the fields they have available. Unset fields don't
    contribute to a match. Tool invocations come through as
    ``tool="git", args=["push", "origin", "main"]``; SQL through
    ``sql="DROP TABLE ..."``; HTTP through ``url=..., http_method=...``.
    """

    tool: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    sql: str | None = None
    url: str | None = None
    http_method: str | None = None


@dataclass(frozen=True)
class DestructiveWhitelist:
    """Parsed whitelist; immutable view of the YAML config."""

    categories: tuple[DestructiveCategory, ...]

    def match(self, action: CandidateAction) -> DestructiveCategory | None:
        """Return the first matching category, or ``None`` if safe."""
        for cat in self.categories:
            if cat.matches(action):
                return cat
        return None

    @classmethod
    def load(cls, path: Path | None = None) -> "DestructiveWhitelist":
        target = path or DEFAULT_CONFIG_PATH
        if not target.is_file():
            return cls(categories=())
        with target.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_raw(data)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "DestructiveWhitelist":
        raw_categories = data.get("destructive_actions") or []
        categories: list[DestructiveCategory] = []
        for entry in raw_categories:
            categories.append(_parse_category(entry))
        return cls(categories=tuple(categories))


def _parse_category(entry: dict[str, Any]) -> DestructiveCategory:
    cid = str(entry["id"])
    description = str(entry.get("description") or cid)
    window = int(entry.get("confirm_window_hours", 4))
    rules: list[MatchRule] = []
    for raw_rule in entry.get("match_any") or []:
        rules.append(_parse_rule(raw_rule))
    return DestructiveCategory(
        id=cid,
        description=description,
        confirm_window_hours=window,
        match_any=tuple(rules),
    )


def _parse_rule(raw: dict[str, Any]) -> MatchRule:
    return MatchRule(
        tool=raw.get("tool"),
        args_contains=_str_tuple(raw.get("args_contains")),
        env_var_set=_str_tuple(raw.get("env_var_set")),
        sql_keyword=_str_tuple(raw.get("sql_keyword")),
        url_contains=_str_tuple(raw.get("url_contains")),
        http_method=raw.get("http_method"),
    )


def _str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(x) for x in value)


def _all_tokens_present(haystack: str, tokens: Iterable[str]) -> bool:
    """True iff every token appears in haystack (order-insensitive)."""
    # Word-boundary match so "main" doesn't match "domain".
    for tok in tokens:
        pattern = re.compile(r"(?:^|[\s/=])" + re.escape(tok) + r"(?:$|[\s/=])")
        if not pattern.search(haystack):
            return False
    return True
