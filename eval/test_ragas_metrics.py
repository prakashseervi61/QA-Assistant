"""Unit tests for the RAGAS evaluation harness (pure logic, no RAGAS dependency)."""

from pathlib import Path

import pytest

from eval.ragas_eval import (
    check_metric_thresholds,
    load_golden_dataset,
    load_results,
    summarize_metrics,
)


class TestGoldenDataset:
    def test_load_golden_dataset(self):
        """Golden dataset loads with required fields."""
        samples = load_golden_dataset(Path("eval/golden_dataset.jsonl"))
        assert len(samples) > 0
        for sample in samples:
            assert "question" in sample
            assert "reference_answer" in sample
            assert "reference_contexts" in sample

    def test_golden_dataset_has_minimum_size(self):
        """At least 5 samples for meaningful metrics."""
        samples = load_golden_dataset(Path("eval/golden_dataset.jsonl"))
        assert len(samples) >= 5


class TestResults:
    def test_load_results(self):
        """Offline results load from JSONL."""
        results = load_results(Path("eval/sample_results.jsonl"))
        assert len(results) > 0
        for r in results:
            assert "question" in r
            assert "answer" in r
            assert "contexts" in r


class TestThresholds:
    def test_all_above_threshold_passes(self):
        metrics = {
            "faithfulness": 0.85,
            "answer_relevancy": 0.9,
            "context_precision": 0.8,
            "context_recall": 0.82,
        }
        assert check_metric_thresholds(metrics) is True

    def test_below_threshold_fails(self):
        metrics = {
            "faithfulness": 0.75,
            "answer_relevancy": 0.9,
            "context_precision": 0.8,
            "context_recall": 0.82,
        }
        assert check_metric_thresholds(metrics) is False

    def test_missing_metric_is_failure(self):
        metrics = {"faithfulness": 0.85}
        assert check_metric_thresholds(metrics) is False

    def test_nan_metric_is_failure(self):
        """NaN must not silently pass the gate (NaN < threshold is False)."""
        metrics = {
            "faithfulness": float("nan"),
            "answer_relevancy": 0.9,
            "context_precision": 0.8,
            "context_recall": 0.82,
        }
        assert check_metric_thresholds(metrics) is False

    def test_nan_in_secondary_metric_is_failure(self):
        """NaN anywhere in the thresholded metrics fails the gate."""
        metrics = {
            "faithfulness": 0.85,
            "answer_relevancy": float("nan"),
            "context_precision": 0.8,
            "context_recall": 0.82,
        }
        assert check_metric_thresholds(metrics) is False


class TestMalformedJsonl:
    def test_load_results_skips_malformed_lines(self, tmp_path):
        """A corrupt JSONL line is skipped with a warning, not fatal."""
        path = tmp_path / "results.jsonl"
        path.write_text(
            '{"question": "q1", "answer": "a1", "contexts": ["c1"]}\n'
            "this is not json\n"
            '{"question": "q2", "answer": "a2", "contexts": ["c2"]}\n',
            encoding="utf-8",
        )
        results = load_results(path)
        assert len(results) == 2
        assert results[0]["question"] == "q1"
        assert results[1]["question"] == "q2"

    def test_load_golden_dataset_skips_malformed_lines(self, tmp_path):
        """Golden dataset loading is equally resilient."""
        path = tmp_path / "golden.jsonl"
        path.write_text(
            '{"question": "q1", "reference_answer": "a1", '
            '"reference_contexts": ["c1"]}\n'
            "{not json\n",
            encoding="utf-8",
        )
        samples = load_golden_dataset(path)
        assert len(samples) == 1
        assert samples[0]["question"] == "q1"


class TestSummarize:
    def test_summarize_averages(self):
        rows = [
            {"faithfulness": 0.8, "answer_relevancy": 0.7},
            {"faithfulness": 0.9, "answer_relevancy": 0.8},
        ]
        summary = summarize_metrics(rows)
        assert summary["faithfulness"] == pytest.approx(0.85)
        assert summary["answer_relevancy"] == pytest.approx(0.75)
