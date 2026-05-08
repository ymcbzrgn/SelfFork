"""LongMemEval dataset loader + scoring harness.

Reference: Wu et al., ICLR 2025, arXiv:2410.10813,
https://github.com/xiaowu0162/LongMemEval (CC BY 4.0).

LongMemEval scores memory across five axes:

1. **info_extraction** — single-session fact recall.
2. **multi_session** — reasoning across multiple sessions.
3. **temporal** — time-aware reasoning ("when did X happen").
4. **knowledge_updates** — handling superseded facts.
5. **abstention** — refusing to answer when memory has no evidence.

This module provides the loader (JSONL → typed dataclasses) and a scoring
harness (predicted answer + reference → per-axis score). The harness is
LLM-judge-pluggable; Order 1 ships an exact-match scorer + a
cosine-similarity scorer (using the configured embedder). LLM-judge
implementation lands alongside Order 2's retriever once it can produce
answers end-to-end.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import numpy as np

__all__ = [
    "LongMemEvalAxis",
    "LongMemEvalJudge",
    "LongMemEvalQuestion",
    "LongMemEvalReport",
    "LongMemEvalScorer",
    "ScoredAnswer",
    "load_longmemeval_dataset",
]


LongMemEvalAxis = Literal[
    "info_extraction",
    "multi_session",
    "temporal",
    "knowledge_updates",
    "abstention",
]


@dataclass(frozen=True, slots=True)
class LongMemEvalQuestion:
    """One question in the LongMemEval corpus."""

    question_id: str
    axis: LongMemEvalAxis
    question: str
    answer: str
    """Reference answer; for ``abstention`` axis this is a refusal string."""

    haystack_session_ids: tuple[str, ...]
    """Sessions whose state the question is grounded in."""


@dataclass(frozen=True, slots=True)
class ScoredAnswer:
    """One question scored under a particular judge."""

    question_id: str
    axis: LongMemEvalAxis
    predicted: str
    reference: str
    score: float
    """0.0 (incorrect) to 1.0 (correct). Judges may produce continuous scores."""


@dataclass(frozen=True, slots=True)
class LongMemEvalReport:
    """Aggregated per-axis scores."""

    per_axis: dict[LongMemEvalAxis, float]
    overall: float
    n_questions: int

    def as_dict(self) -> dict[str, object]:
        return {
            "n_questions": self.n_questions,
            "overall": self.overall,
            "per_axis": dict(self.per_axis),
        }


@runtime_checkable
class LongMemEvalJudge(Protocol):
    """Judges a single (predicted, reference) pair on the [0.0, 1.0] axis."""

    async def judge(
        self,
        *,
        question: LongMemEvalQuestion,
        predicted: str,
    ) -> float: ...


# ── Built-in judges ────────────────────────────────────────────────────────


class ExactMatchJudge:
    """Strict normalised string-equality judge.

    Lowercases, strips, collapses whitespace; returns 1.0 if equal else 0.0.
    Used as a regression-floor judge — high precision, brittle.
    """

    async def judge(
        self,
        *,
        question: LongMemEvalQuestion,
        predicted: str,
    ) -> float:
        return 1.0 if _normalise(predicted) == _normalise(question.answer) else 0.0


class CosineEmbeddingJudge:
    """Cosine similarity over the configured embedder.

    Returns ``max(0.0, cos(predicted, reference))``. Useful for partial
    credit on free-form answers; calibrate the threshold per axis if you
    use this for accept/reject decisions.
    """

    def __init__(
        self,
        *,
        embed_query: Callable[[str], Awaitable[Sequence[float]]],
    ) -> None:
        self._embed_query = embed_query

    async def judge(
        self,
        *,
        question: LongMemEvalQuestion,
        predicted: str,
    ) -> float:
        pred_vec = np.asarray(await self._embed_query(predicted), dtype=np.float32)
        ref_vec = np.asarray(await self._embed_query(question.answer), dtype=np.float32)
        denom = float(np.linalg.norm(pred_vec) * np.linalg.norm(ref_vec))
        if denom == 0.0:
            return 0.0
        return float(max(0.0, np.dot(pred_vec, ref_vec) / denom))


# ── Loader ─────────────────────────────────────────────────────────────────


def load_longmemeval_dataset(
    dataset_path: Path,
) -> list[LongMemEvalQuestion]:
    """Read a LongMemEval JSONL file into typed questions.

    Expected line shape (matches the public dataset):

    .. code-block:: json

        {
            "question_id": "...",
            "axis": "info_extraction",
            "question": "...",
            "answer": "...",
            "haystack_session_ids": ["s1", "s2"]
        }

    Lines that fail validation are silently skipped — a malformed corpus
    must not crash the eval harness.
    """
    out: list[LongMemEvalQuestion] = []
    with dataset_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            try:
                out.append(_parse_question(payload))
            except (KeyError, ValueError, TypeError):
                continue
    return out


# ── Scorer ─────────────────────────────────────────────────────────────────


class LongMemEvalScorer:
    """Runs a judge across a question set and aggregates the report."""

    def __init__(self, *, judge: LongMemEvalJudge) -> None:
        self._judge = judge

    async def score(
        self,
        *,
        questions: Sequence[LongMemEvalQuestion],
        predictions: dict[str, str],
    ) -> LongMemEvalReport:
        """Score a batch of predictions against reference answers.

        ``predictions`` maps ``question_id`` → predicted-answer string.
        Missing predictions are scored 0.0 (treated as wrong).
        """
        scored: list[ScoredAnswer] = []
        for q in questions:
            predicted = predictions.get(q.question_id, "")
            score = await self._judge.judge(question=q, predicted=predicted)
            scored.append(
                ScoredAnswer(
                    question_id=q.question_id,
                    axis=q.axis,
                    predicted=predicted,
                    reference=q.answer,
                    score=score,
                ),
            )
        return _aggregate(scored)


# ── helpers ────────────────────────────────────────────────────────────────


_VALID_AXES: frozenset[str] = frozenset(
    [
        "info_extraction",
        "multi_session",
        "temporal",
        "knowledge_updates",
        "abstention",
    ],
)


def _parse_question(payload: dict[str, object]) -> LongMemEvalQuestion:
    axis = payload["axis"]
    if not isinstance(axis, str) or axis not in _VALID_AXES:
        raise ValueError(f"Invalid axis: {axis!r}")
    haystack = payload.get("haystack_session_ids", [])
    if not isinstance(haystack, list):
        raise TypeError("haystack_session_ids must be a list")
    question_id = payload["question_id"]
    question = payload["question"]
    answer = payload["answer"]
    if not (isinstance(question_id, str) and isinstance(question, str) and isinstance(answer, str)):
        raise TypeError("required string fields missing or wrong type")
    return LongMemEvalQuestion(
        question_id=question_id,
        axis=axis,  # type: ignore[arg-type]
        question=question,
        answer=answer,
        haystack_session_ids=tuple(str(s) for s in haystack),
    )


def _normalise(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _aggregate(scored: Sequence[ScoredAnswer]) -> LongMemEvalReport:
    if not scored:
        return LongMemEvalReport(
            per_axis={},
            overall=0.0,
            n_questions=0,
        )
    by_axis: dict[LongMemEvalAxis, list[float]] = {}
    for s in scored:
        by_axis.setdefault(s.axis, []).append(s.score)
    per_axis: dict[LongMemEvalAxis, float] = {
        axis: sum(vals) / len(vals) for axis, vals in by_axis.items()
    }
    overall = sum(s.score for s in scored) / len(scored)
    return LongMemEvalReport(
        per_axis=per_axis,
        overall=overall,
        n_questions=len(scored),
    )
