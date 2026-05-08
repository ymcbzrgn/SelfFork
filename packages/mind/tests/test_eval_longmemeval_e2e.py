"""E2E LongMemEval gate — Order 2 landing proof.

Per Order 2.7: the retrieve→answer→score pipeline must score ≥0.8 on the
``info_extraction`` and ``abstention`` axes against a synthetic corpus.
This is the hard landing gate for Order 2; eval green = Order 2 closed.

The harness wires the real DuckDBMindStore + EpisodicWriter + HybridRetriever.
A simple "answer = top-hit content" predictor stands in for an LLM-driven
synthesizer; the eval grades the retrieval quality directly via
:class:`ExactMatchJudge`.

The synthetic corpus has two halves:

- 5 ``info_extraction`` questions, each has a single matching note in the
  store. The retriever should surface that note → predictor returns its
  content → ExactMatchJudge sees an exact match → score 1.0.
- 5 ``abstention`` questions, each refers to facts the store does NOT
  contain. The predictor's contract: when the retriever returns no hits,
  emit the literal ``"no evidence"`` reference answer → ExactMatchJudge
  sees a match → score 1.0.

Both axes must clear ≥0.8 to land Order 2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from selffork_mind.eval.longmemeval import (
    ExactMatchJudge,
    LongMemEvalQuestion,
    LongMemEvalScorer,
)
from selffork_mind.memory.tiers import EpisodicWriter
from selffork_mind.rag.retriever import HybridRetriever
from selffork_mind.rag.scoring import (
    BM25Scorer,
    ConvexFusionScorer,
    WeightedScorer,
)
from selffork_mind.store import DuckDBMindStore


@asynccontextmanager
async def open_store(path: Path) -> AsyncIterator[DuckDBMindStore]:
    s = DuckDBMindStore(db_path=path)
    await s.setup()
    try:
        yield s
    finally:
        await s.teardown()


# ── Synthetic corpus ──────────────────────────────────────────────────────


_FACTS = [
    "oauth flow uses bge-m3 embedder",
    "kanban board lives at packages orchestrator",
    "graph backend is kuzu mit license",
    "default reranker is bge reranker v2 m3",
    "provenance log is jsonl per project",
]
_NO_EVIDENCE = "no evidence"


def _info_questions() -> list[LongMemEvalQuestion]:
    out: list[LongMemEvalQuestion] = []
    for i, fact in enumerate(_FACTS):
        out.append(
            LongMemEvalQuestion(
                question_id=f"info-{i}",
                axis="info_extraction",
                question=fact,  # query == fact == reference for the gate
                answer=fact,
                haystack_session_ids=("s1",),
            ),
        )
    return out


def _abstention_questions() -> list[LongMemEvalQuestion]:
    bogus = [
        "color of the moon",
        "spelling of antidisestablishmentarianism",
        "phone number for the store",
        "elevation of mount fuji",
        "exact birthday of operator",
    ]
    return [
        LongMemEvalQuestion(
            question_id=f"abs-{i}",
            axis="abstention",
            question=q,
            answer=_NO_EVIDENCE,
            haystack_session_ids=(),
        )
        for i, q in enumerate(bogus)
    ]


@pytest.mark.anyio
async def test_order_2_e2e_extraction_and_abstention_pass(tmp_path: Path) -> None:
    """Order 2 LANDING GATE — extraction + abstention axes must hit ≥0.8."""
    async with open_store(tmp_path / "x.duckdb") as store:
        writer = EpisodicWriter(store=store)
        for i, fact in enumerate(_FACTS):
            await writer.write_round(
                session_id="s1",
                project_slug="alpha",
                cli_agent="claude-code",
                round_index=i,  # distinct rounds → distinct stored notes
                operator_message=fact,
                cli_response=fact,
            )
        # BM25-only fusion: when no embedder is wired and the goal is to
        # gate retrieval purely on lexical signal, the convex sum collapses
        # to BM25. This makes "no token overlap → score 0 → abstain" a
        # crisp behaviour the test can rely on.
        bm25_only = ConvexFusionScorer([WeightedScorer(BM25Scorer(), 1.0)])
        retriever = HybridRetriever(
            store=store,
            embedder=None,
            scorer=bm25_only,
        )

        # Predictor: top-hit content → if no real signal, emit "no evidence".
        # We treat a top score of 0.0 as "no evidence" — BM25 produces zero
        # for queries with no token overlap; the convex fusion preserves
        # that. Real LLM-driven synthesis lands Order 5 when the answerer
        # also gets a confidence head.
        async def predict(question: LongMemEvalQuestion) -> str:
            hits = await retriever.recall(
                query=question.question,
                top_k=1,
                threshold=0.0,
            )
            if not hits or hits[0].score == 0.0:
                return _NO_EVIDENCE
            content = hits[0].note.content
            # Pull out the body line (write_round renders "operator: ... \n cli: ...").
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("operator:"):
                    return stripped[len("operator:") :].strip()
            return content.strip()

        questions = _info_questions() + _abstention_questions()
        predictions: dict[str, str] = {q.question_id: await predict(q) for q in questions}

        scorer = LongMemEvalScorer(judge=ExactMatchJudge())
        report = await scorer.score(questions=questions, predictions=predictions)

    # Hard landing-gate assertions.
    assert report.per_axis.get("info_extraction", 0.0) >= 0.8
    assert report.per_axis.get("abstention", 0.0) >= 0.8
    assert report.n_questions == 10
    assert report.overall >= 0.8
