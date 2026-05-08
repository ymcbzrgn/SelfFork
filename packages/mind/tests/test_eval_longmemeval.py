"""Tests for :mod:`selffork_mind.eval.longmemeval`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from selffork_mind.eval.longmemeval import (
    ExactMatchJudge,
    LongMemEvalQuestion,
    LongMemEvalScorer,
    load_longmemeval_dataset,
)


class TestLoader:
    def test_loads_well_formed_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "data.jsonl"
        path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "question_id": "q1",
                            "axis": "info_extraction",
                            "question": "Operator's preferred embedder?",
                            "answer": "BGE-M3",
                            "haystack_session_ids": ["s1", "s2"],
                        },
                    ),
                    json.dumps(
                        {
                            "question_id": "q2",
                            "axis": "abstention",
                            "question": "Operator's favourite ice cream?",
                            "answer": "Not stated in any session.",
                            "haystack_session_ids": ["s1"],
                        },
                    ),
                ],
            ),
            encoding="utf-8",
        )
        questions = load_longmemeval_dataset(path)
        assert len(questions) == 2
        assert questions[0].axis == "info_extraction"
        assert questions[1].axis == "abstention"

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "data.jsonl"
        path.write_text(
            "not-json\n"
            + json.dumps(
                {
                    "question_id": "q1",
                    "axis": "info_extraction",
                    "question": "x",
                    "answer": "y",
                    "haystack_session_ids": [],
                },
            ),
            encoding="utf-8",
        )
        questions = load_longmemeval_dataset(path)
        assert len(questions) == 1

    def test_invalid_axis_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "data.jsonl"
        path.write_text(
            json.dumps(
                {
                    "question_id": "q1",
                    "axis": "not-a-real-axis",
                    "question": "x",
                    "answer": "y",
                    "haystack_session_ids": [],
                },
            ),
            encoding="utf-8",
        )
        assert load_longmemeval_dataset(path) == []


class TestExactMatchJudge:
    @pytest.mark.anyio
    async def test_normalised_match(self) -> None:
        q = LongMemEvalQuestion(
            question_id="q",
            axis="info_extraction",
            question="?",
            answer="BGE-M3",
            haystack_session_ids=(),
        )
        judge = ExactMatchJudge()
        assert await judge.judge(question=q, predicted="bge-m3") == 1.0
        assert await judge.judge(question=q, predicted="  BGE-M3  ") == 1.0
        assert await judge.judge(question=q, predicted="OpenAI") == 0.0


class TestScorer:
    @pytest.mark.anyio
    async def test_aggregates_per_axis(self) -> None:
        questions = [
            LongMemEvalQuestion("q1", "info_extraction", "?", "a", ()),
            LongMemEvalQuestion("q2", "info_extraction", "?", "b", ()),
            LongMemEvalQuestion("q3", "abstention", "?", "no", ()),
        ]
        predictions = {"q1": "a", "q2": "wrong", "q3": "no"}
        scorer = LongMemEvalScorer(judge=ExactMatchJudge())
        report = await scorer.score(questions=questions, predictions=predictions)
        assert report.n_questions == 3
        assert report.per_axis["info_extraction"] == pytest.approx(0.5)
        assert report.per_axis["abstention"] == pytest.approx(1.0)
        assert report.overall == pytest.approx(2 / 3)

    @pytest.mark.anyio
    async def test_missing_predictions_score_zero(self) -> None:
        questions = [
            LongMemEvalQuestion("q1", "info_extraction", "?", "a", ()),
            LongMemEvalQuestion("q2", "info_extraction", "?", "b", ()),
        ]
        predictions = {"q1": "a"}
        scorer = LongMemEvalScorer(judge=ExactMatchJudge())
        report = await scorer.score(questions=questions, predictions=predictions)
        assert report.per_axis["info_extraction"] == pytest.approx(0.5)
