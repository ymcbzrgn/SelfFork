"""Tests for :mod:`selffork_mind.historian` -- deterministic decision recall.

Covers, with synthetic markdown fixtures in ``tmp_path``:

- indexing produces correct ``path:line`` citations (title anchored at line 1);
- recall returns the right decision for English + Turkish queries;
- a citation resolves to the matched *sub-section* heading, not just the title;
- empty / missing directories and malformed (heading-less / unreadable) docs
  are handled without crashing;
- ``top_k`` bounds and empty queries;
- the continuity digest.

Plus one integration test against the REAL ``docs/decisions`` tree, asserting
it indexes several decisions with well-formed citations.
"""

from __future__ import annotations

from pathlib import Path

from selffork_mind.historian import (
    DecisionHit,
    Historian,
    index_decisions,
    tokenize,
)

# Repo root = .../SelfFork ; this file is packages/mind/tests/test_historian.py.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_DECISIONS_DIR = _REPO_ROOT / "docs" / "decisions"
_REAL_ARCHIVE = _REPO_ROOT / "docs" / "archive" / "Yamac_Jr_Nano_Kararlar.md"


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def _adr_retry(path: Path) -> str:
    """A synthetic ADR with a distinctive sub-section heading."""
    body = (
        "# ADR-042 - Retry Policy\n"
        "\n"
        "## Status\n"
        "\n"
        "- **Status:** Accepted (2026-06-01)\n"
        "\n"
        "## Context\n"
        "\n"
        "We need a retry policy for flaky network calls.\n"
        "\n"
        "## Decision\n"
        "\n"
        "Use exponential backoff for transient failures.\n"
        "\n"
        "### Retry Backoff Schedule\n"
        "\n"
        "The schedule doubles the delay on each attempt.\n"
        "\n"
        "### Circuit Breaker\n"
        "\n"
        "Open the circuit after five consecutive failures.\n"
    )
    _write(path, body)
    return body


def _adr_cache(path: Path) -> str:
    body = (
        "# ADR-043: Cache Eviction Strategy\n"
        "\n"
        "**Status:** Proposed (2026-06-05)\n"
        "\n"
        "## Decision\n"
        "\n"
        "Evict cache entries with a least-recently-used policy.\n"
    )
    _write(path, body)
    return body


def _adr_turkish(path: Path) -> str:
    # Turkish letters (i-dotless, s-cedilla, c-cedilla) are allowed confusables.
    body = (
        "# ADR-099 - Bellek Kapsam Karari\n"
        "\n"
        "## Status\n"
        "\n"
        "- **Status:** Onaylandi (2026-06-15)\n"
        "\n"
        "## Baglam\n"
        "\n"
        "Proje bazli ve global bellek havuzlari gerekiyor.\n"
        "\n"
        "## Karar\n"
        "\n"
        "Dual-pool bellek kapsami kullanilacak.\n"
    )
    _write(path, body)
    return body


# --------------------------------------------------------------------------- #
# tokenizer                                                                    #
# --------------------------------------------------------------------------- #


def test_tokenize_splits_and_lowercases() -> None:
    assert tokenize("ADR-042 Retry_Policy backoff") == [
        "adr",
        "042",
        "retry",
        "policy",
        "backoff",
    ]


def test_tokenize_handles_turkish() -> None:
    assert tokenize("Bellek Kapsami") == ["bellek", "kapsami"]


# --------------------------------------------------------------------------- #
# indexing + citations                                                        #
# --------------------------------------------------------------------------- #


def test_index_produces_title_citation_at_line_one(tmp_path: Path) -> None:
    adr = tmp_path / "ADR-042_Retry.md"
    _adr_retry(adr)

    decisions = index_decisions(tmp_path)
    assert len(decisions) == 1

    decision = decisions[0]
    assert decision.id == "ADR-042"
    assert decision.title == "ADR-042 - Retry Policy"
    assert decision.line == 1
    assert decision.status == "Accepted (2026-06-01)"
    assert decision.date == "2026-06-01"
    assert "retry" in decision.summary.lower()
    # Citation is posix ``path:line`` anchored at the title heading.
    assert decision.citation == f"{decision.path}:1"
    assert decision.path.endswith("ADR-042_Retry.md")
    assert "\\" not in decision.path


def test_index_is_sorted_and_multi_file(tmp_path: Path) -> None:
    _adr_retry(tmp_path / "ADR-042_Retry.md")
    _adr_cache(tmp_path / "ADR-043_Cache.md")

    decisions = index_decisions(tmp_path)
    assert [d.id for d in decisions] == ["ADR-042", "ADR-043"]
    # Second ADR uses the bare ``**Status:**`` style (no leading bullet).
    assert decisions[1].status == "Proposed (2026-06-05)"
    assert decisions[1].date == "2026-06-05"


def test_status_absent_is_none(tmp_path: Path) -> None:
    _write(tmp_path / "note.md", "# Title Only\n\nSome prose but no status line.\n")
    decision = index_decisions(tmp_path)[0]
    assert decision.status is None
    assert decision.date is None
    assert decision.id == "note"  # falls back to the file stem


# --------------------------------------------------------------------------- #
# recall                                                                       #
# --------------------------------------------------------------------------- #


def test_recall_returns_right_decision(tmp_path: Path) -> None:
    _adr_retry(tmp_path / "ADR-042_Retry.md")
    _adr_cache(tmp_path / "ADR-043_Cache.md")
    historian = Historian.from_dir(tmp_path)

    hits = historian.recall("cache eviction")
    assert hits, "expected at least one hit"
    top = hits[0]
    assert isinstance(top, DecisionHit)
    assert top.decision.id == "ADR-043"
    assert top.citation.endswith("ADR-043_Cache.md:1")


def test_recall_cites_matched_subheading(tmp_path: Path) -> None:
    body = _adr_retry(tmp_path / "ADR-042_Retry.md")
    expected_line = body.splitlines().index("### Retry Backoff Schedule") + 1
    historian = Historian.from_dir(tmp_path)

    hits = historian.recall("backoff schedule")
    assert hits
    top = hits[0]
    assert top.decision.id == "ADR-042"
    assert top.matched_heading == "Retry Backoff Schedule"
    assert top.line == expected_line
    assert top.citation.endswith(f"ADR-042_Retry.md:{expected_line}")


def test_recall_turkish_query(tmp_path: Path) -> None:
    _adr_turkish(tmp_path / "ADR-099_Bellek.md")
    _adr_cache(tmp_path / "ADR-043_Cache.md")
    historian = Historian.from_dir(tmp_path)

    hits = historian.recall("bellek kapsam")
    assert hits
    assert hits[0].decision.id == "ADR-099"


def test_recall_by_adr_id(tmp_path: Path) -> None:
    _adr_retry(tmp_path / "ADR-042_Retry.md")
    _adr_cache(tmp_path / "ADR-043_Cache.md")
    historian = Historian.from_dir(tmp_path)

    hits = historian.recall("what did we decide in ADR-043")
    assert hits
    assert hits[0].decision.id == "ADR-043"


def test_recall_respects_top_k(tmp_path: Path) -> None:
    _adr_retry(tmp_path / "ADR-042_Retry.md")
    _adr_cache(tmp_path / "ADR-043_Cache.md")
    _adr_turkish(tmp_path / "ADR-099_Bellek.md")
    historian = Historian.from_dir(tmp_path)

    assert len(historian.recall("decision", top_k=2)) <= 2
    assert historian.recall("decision", top_k=0) == []


def test_recall_empty_query_returns_empty(tmp_path: Path) -> None:
    _adr_cache(tmp_path / "ADR-043_Cache.md")
    historian = Historian.from_dir(tmp_path)
    assert historian.recall("") == []
    assert historian.recall("   ") == []


def test_recall_no_match_returns_empty(tmp_path: Path) -> None:
    _adr_cache(tmp_path / "ADR-043_Cache.md")
    historian = Historian.from_dir(tmp_path)
    assert historian.recall("quantum chromodynamics telemetry") == []


def test_recall_is_deterministic(tmp_path: Path) -> None:
    _adr_retry(tmp_path / "ADR-042_Retry.md")
    _adr_cache(tmp_path / "ADR-043_Cache.md")
    historian = Historian.from_dir(tmp_path)

    first = [(h.decision.id, h.line, h.score) for h in historian.recall("decision policy")]
    second = [(h.decision.id, h.line, h.score) for h in historian.recall("decision policy")]
    assert first == second


# --------------------------------------------------------------------------- #
# robustness: empty / missing / malformed                                     #
# --------------------------------------------------------------------------- #


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert index_decisions(tmp_path / "does_not_exist") == []
    historian = Historian.from_dir(tmp_path / "does_not_exist")
    assert historian.decisions == ()
    assert historian.recall("anything") == []


def test_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert index_decisions(tmp_path) == []


def test_malformed_doc_is_skipped_not_crashed(tmp_path: Path) -> None:
    # Heading-less doc + empty doc are skipped; the valid ADR still indexes.
    _write(tmp_path / "no_heading.md", "just some text\nwith no markdown heading\n")
    _write(tmp_path / "empty.md", "")
    _adr_cache(tmp_path / "ADR-043_Cache.md")

    decisions = index_decisions(tmp_path)
    assert [d.id for d in decisions] == ["ADR-043"]


def test_fenced_hash_is_not_a_heading(tmp_path: Path) -> None:
    body = (
        "# ADR-050 - Shell Rules\n"
        "\n"
        "## Decision\n"
        "\n"
        "```bash\n"
        "# this is a shell comment, not a heading\n"
        "echo hi\n"
        "```\n"
    )
    _write(tmp_path / "ADR-050_Shell.md", body)
    decision = index_decisions(tmp_path)[0]
    headings = [section.heading for section in decision.sections]
    assert headings == ["ADR-050 - Shell Rules", "Decision"]


# --------------------------------------------------------------------------- #
# archive + continuity                                                         #
# --------------------------------------------------------------------------- #


def test_archive_is_indexed(tmp_path: Path) -> None:
    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir()
    _adr_cache(decisions_dir / "ADR-043_Cache.md")
    archive = tmp_path / "archive.md"
    _write(
        archive,
        "# Nano Kararlar\n\n# 9. Loss stratejisi\n\nLoss agirliklari belirlendi.\n",
    )

    decisions = index_decisions(decisions_dir, archive=archive)
    ids = [d.id for d in decisions]
    assert "ADR-043" in ids
    assert "archive" in ids  # stem of archive.md

    historian = Historian(decisions)
    hits = historian.recall("loss stratejisi")
    assert hits
    assert hits[0].decision.id == "archive"
    assert hits[0].matched_heading == "9. Loss stratejisi"


def test_continuity_summary(tmp_path: Path) -> None:
    _adr_retry(tmp_path / "ADR-042_Retry.md")  # 2026-06-01
    _adr_cache(tmp_path / "ADR-043_Cache.md")  # 2026-06-05
    historian = Historian.from_dir(tmp_path)

    summary = historian.continuity_summary(limit=1)
    # Most recent by date is ADR-043 (2026-06-05).
    assert "ADR-043" in summary
    assert "ADR-042" not in summary
    assert ".md:" in summary  # carries a citation


def test_continuity_summary_empty() -> None:
    assert Historian([]).continuity_summary() == "No decisions on record."


# --------------------------------------------------------------------------- #
# integration: real decision docs                                             #
# --------------------------------------------------------------------------- #


def test_real_decisions_index_with_valid_citations() -> None:
    assert _REAL_DECISIONS_DIR.is_dir(), "real decisions dir must exist"
    archive = _REAL_ARCHIVE if _REAL_ARCHIVE.is_file() else None

    decisions = index_decisions(_REAL_DECISIONS_DIR, archive=archive)
    assert len(decisions) >= 10, "expected the real ADR corpus to index"

    ids = {d.id for d in decisions}
    assert "ADR-008" in ids
    assert "ADR-002" in ids

    for decision in decisions:
        path_part, _, line_part = decision.citation.rpartition(":")
        assert path_part.endswith(".md")
        assert line_part.isdigit()
        assert int(line_part) >= 1
        assert decision.line >= 1


def test_real_recall_distinctive_titles() -> None:
    archive = _REAL_ARCHIVE if _REAL_ARCHIVE.is_file() else None
    historian = Historian.from_dir(_REAL_DECISIONS_DIR, archive=archive)

    # Each token is unique to exactly one real ADR title, so the title weight
    # dominates any incidental body mention in other docs.
    assert historian.recall("heartbeat")[0].decision.id == "ADR-008"
    assert historian.recall("surfing")[0].decision.id == "ADR-003"
    assert historian.recall("resilience")[0].decision.id == "ADR-011"

    # Every real-doc hit must carry a well-formed path:line citation.
    hit = historian.recall("heartbeat")[0]
    assert hit.citation.endswith(f":{hit.line}")
    assert hit.line >= 1
