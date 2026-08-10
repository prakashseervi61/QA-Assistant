"""RAGAS evaluation harness for the QA-Assistant RAG pipeline.

Run:
    python eval/ragas_eval.py --sample 3           # live mode (runs pipeline)
    python eval/ragas_eval.py --offline results.jsonl  # offline mode (pre-generated)

Offline mode lets CI evaluate without a live RAG service or LLM keys.
Requires: pip install ragas datasets (lazy-import; clear error if missing).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Metric thresholds (roadmap: faithfulness > 0.8)
DEFAULT_THRESHOLDS = {
    "faithfulness": 0.8,
    "answer_relevancy": 0.5,
    "context_precision": 0.5,
    "context_recall": 0.5,
}

GOLDEN_DATASET_PATH = Path(__file__).parent / "golden_dataset.jsonl"


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    """Load rows from a JSONL file, skipping malformed lines with a warning.

    A single corrupt line must not crash the whole evaluation, so each
    line is parsed independently and the offending line number is logged.
    """
    rows: list[dict[str, object]] = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping malformed JSON line %d in %s: %s", line_no, path, exc
                )
    return rows


def load_golden_dataset(path: Path) -> list[dict[str, object]]:
    """Load golden QA samples from a JSONL file."""
    return _load_jsonl(path)


def load_results(path: Path) -> list[dict[str, object]]:
    """Load pre-generated RAG results from a JSONL file."""
    return _load_jsonl(path)


def check_metric_thresholds(
    metrics: dict[str, float],
    thresholds: dict[str, float] | None = None,
) -> bool:
    """Return True if all metrics meet thresholds; False otherwise."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    for name, threshold in thresholds.items():
        value = metrics.get(name)
        if value is None:
            logger.warning("Metric %s missing - treating as failure", name)
            return False
        # NaN comparisons are always False, so a NaN value would silently
        # pass the gate. Treat NaN as a failure explicitly.
        if isinstance(value, float) and math.isnan(value):
            logger.warning("Metric %s is NaN - treating as failure", name)
            return False
        if value < threshold:
            logger.warning(
                "Metric %s = %.3f below threshold %.2f", name, value, threshold
            )
            return False
    return True


def summarize_metrics(rows: list[dict[str, object]]) -> dict[str, float]:
    """Average numeric metrics across result rows."""
    summary: dict[str, float] = {}
    keys = set()
    for row in rows:
        keys.update(k for k, v in row.items() if isinstance(v, (int, float)))
    for key in sorted(keys):
        values = [
            float(row[key]) for row in rows if isinstance(row.get(key), (int, float))
        ]
        if values:
            summary[key] = sum(values) / len(values)
    return summary


def _build_query_use_case() -> object:
    """Build the query use case exactly like the FastAPI app does.

    Mirrors ``src.presentation.api.app._wire_dependencies()`` so the eval
    harness exercises the same pipeline the API serves.
    """
    from src.application.services.rag_engine import RAGEngine
    from src.application.use_cases.query_document import QueryDocumentUseCase
    from src.infrastructure.config.settings import get_settings
    from src.infrastructure.embeddings.factory import EmbeddingProviderFactory
    from src.infrastructure.llm.factory import LLMProviderFactory
    from src.infrastructure.llm.query_rewriter_factory import (
        create_query_rewriter,
    )
    from src.infrastructure.observability.tracer import create_tracer
    from src.infrastructure.repositories.memory_conversation_repository import (
        MemoryConversationRepository,
    )
    from src.infrastructure.rerankers.factory import create_reranker
    from src.infrastructure.vector_store.chroma_store import ChromaStore

    settings = get_settings()
    llm_provider = LLMProviderFactory.create(settings)
    embedding_provider = EmbeddingProviderFactory.create(settings)
    vector_store = ChromaStore(persist_directory=settings.CHROMA_PERSIST_DIR)
    reranker = create_reranker()
    query_rewriter = create_query_rewriter(
        llm_provider, embedding_provider, vector_store
    )
    tracer = create_tracer()
    rag_engine = RAGEngine(
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        reranker=reranker,
        query_rewriter=query_rewriter,
        tracer=tracer,
    )
    conversation_repository = MemoryConversationRepository()
    return QueryDocumentUseCase(rag_engine, conversation_repository)


async def _evaluate_samples(
    use_case: object,
    samples: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Run the pipeline over each sample and collect metric input rows."""
    rows: list[dict[str, object]] = []
    for item in samples:
        question = str(item["question"])
        logger.info("Evaluating question: %s", question)
        result = await use_case.execute(question=question)
        sources = result.get("sources", [])
        contexts = [str(src["content"]) for src in sources if "content" in src]
        rows.append(
            {
                "question": question,
                "answer": str(result.get("answer", "")),
                "contexts": contexts,
                "reference_answer": str(item.get("reference_answer", "")),
                "reference_contexts": [
                    str(c) for c in item.get("reference_contexts", [])
                ],
            }
        )
    return rows


def run_live_eval(sample: int | None = None) -> list[dict[str, object]]:
    """Run the RAG pipeline over the golden dataset and return input rows."""
    use_case = _build_query_use_case()
    samples = load_golden_dataset(GOLDEN_DATASET_PATH)
    if sample is not None:
        samples = samples[:sample]
    return asyncio.run(_evaluate_samples(use_case, samples))


def run_offline_eval(results_path: Path) -> list[dict[str, object]]:
    """Compute metric input rows from pre-generated results (no pipeline).

    Merges each result with the golden dataset by question so that
    ``reference_answer`` / ``reference_contexts`` are available for the
    context metrics. Results not found in the golden dataset are included
    with empty references (their context metrics will score low or NaN).
    """
    results = load_results(results_path)
    golden_by_question = {
        str(sample.get("question", "")).strip(): sample
        for sample in load_golden_dataset(GOLDEN_DATASET_PATH)
    }
    rows: list[dict[str, object]] = []
    for result in results:
        question = str(result.get("question", "")).strip()
        golden = golden_by_question.get(question, {})
        rows.append(
            {
                "question": question,
                "answer": str(result.get("answer", "")),
                "contexts": [str(c) for c in result.get("contexts", [])],
                "reference_answer": str(golden.get("reference_answer", "")),
                "reference_contexts": [
                    str(c) for c in golden.get("reference_contexts", [])
                ],
            }
        )
    return rows


def compute_ragas_metrics(
    rows: list[dict[str, object]],
) -> list[dict[str, float]]:
    """Compute RAGAS metrics for the given rows (lazy-import ragas)."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS evaluation requires ragas and datasets. "
            "Install with: pip install ragas datasets"
        ) from exc

    ragas_dataset = Dataset.from_list(
        [
            {
                "question": str(row["question"]),
                "answer": str(row["answer"]),
                "contexts": [str(c) for c in row["contexts"]],
                "ground_truth": str(row["reference_answer"]),
                "reference": [str(c) for c in row["reference_contexts"]],
            }
            for row in rows
        ]
    )
    result = evaluate(
        ragas_dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )
    records = result.to_pandas().to_dict("records")
    return [dict(record) for record in records]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAGAS evaluation for QA-Assistant")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Run on the first N golden questions only",
    )
    parser.add_argument(
        "--offline",
        type=str,
        default=None,
        help="Path to pre-generated results JSONL (skip live pipeline)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the faithfulness threshold (default 0.8)",
    )
    args = parser.parse_args(argv)

    thresholds = dict(DEFAULT_THRESHOLDS)
    if args.threshold is not None:
        thresholds["faithfulness"] = args.threshold

    if args.offline:
        rows = run_offline_eval(Path(args.offline))
    else:
        rows = run_live_eval(sample=args.sample)

    if not rows:
        logger.error("No evaluation rows produced - aborting")
        return 2

    metric_rows = compute_ragas_metrics(rows)
    summary = summarize_metrics(metric_rows)

    print("\n=== RAGAS Evaluation Summary ===")
    for name in sorted(summary):
        print(f"  {name:<24} {summary[name]:.4f}")
    print("================================\n")

    ok = check_metric_thresholds(summary, thresholds)
    if not ok:
        logger.error("Evaluation FAILED - metrics below thresholds: %s", thresholds)
        return 1
    print("All metrics above thresholds. PASS.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main())
