"""Project slug normalization + validation.

A slug is the filesystem-safe id derived from a project's display name.
We use it for directory names under ``~/.selffork/projects/<slug>/`` and
as the URL path segment in the dashboard (``/projects/?slug=...``), so
it must be POSIX-safe + URL-safe.

Rules (locked-in, change-resistant):

- Lowercase only.
- Allowed characters: ``[a-z0-9-]``.
- Word boundaries collapse to a single dash; leading/trailing dashes
  are stripped.
- Unicode letters are romanized via ``unicodedata.normalize`` to NFKD
  then ASCII-stripped — e.g. "Yamaç Jr" → "yamac-jr" rather than
  exploding into noise.
- Min length 1, max length 64. Anything outside that range is invalid.
- A handful of reserved slugs are rejected so they can never collide
  with other top-level path segments (``new``, ``api``, ``audit``).
"""

from __future__ import annotations

import re
import unicodedata

from selffork_shared.errors import ConfigError

__all__ = ["MAX_SLUG_LEN", "RESERVED_SLUGS", "normalize_slug", "validate_slug"]

MAX_SLUG_LEN = 64

# Slugs we won't allow for projects because the dashboard reserves
# them as routes or top-level dirs. Future additions here are
# breaking changes — be deliberate.
RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        "new",
        "api",
        "audit",
        "run",
        "session",
        "sessions",
        "scheduled",
        "projects",
        "settings",
        "health",
    },
)

_SLUG_VALID = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_SLUG_BUILD = re.compile(r"[^a-z0-9]+")


def normalize_slug(name: str) -> str:
    """Convert ``name`` into a slug. Raises :class:`ConfigError` if empty.

    The function is deterministic and idempotent: ``normalize_slug(s)``
    where ``s`` is already a valid slug returns ``s`` unchanged.
    """
    if not name:
        raise ConfigError("project name cannot be empty")
    # NFKD + ASCII strip handles ç → c, ş → s, etc.
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    collapsed = _SLUG_BUILD.sub("-", lowered).strip("-")
    if not collapsed:
        raise ConfigError(
            f"project name {name!r} produces an empty slug; pick a name "
            "with at least one ASCII letter or digit",
        )
    return collapsed[:MAX_SLUG_LEN].rstrip("-")


def validate_slug(slug: str) -> None:
    """Raise :class:`ConfigError` if ``slug`` isn't usable.

    A separate validator from :func:`normalize_slug` so callers loading
    a slug from disk (where it should already be valid) can fail loudly
    instead of silently coercing.
    """
    if not slug:
        raise ConfigError("slug is empty")
    if len(slug) > MAX_SLUG_LEN:
        raise ConfigError(
            f"slug {slug!r} exceeds {MAX_SLUG_LEN} characters",
        )
    if not _SLUG_VALID.match(slug):
        raise ConfigError(
            f"slug {slug!r} contains invalid characters; allowed: a-z 0-9 -",
        )
    if slug in RESERVED_SLUGS:
        raise ConfigError(
            f"slug {slug!r} is reserved; pick a different project name",
        )
