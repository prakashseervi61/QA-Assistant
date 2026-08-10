# Evaluation: RAGAS Quality Harness

This directory contains an **offline evaluation harness** for the RAG pipeline.
It measures retrieval-and-generation quality against a curated golden dataset
using [RAGAS](https://docs.ragas.io/) metrics:

| Metric | Meaning | Default threshold |
|---|---|---|
| `faithfulness` | Are the answer's claims supported by the retrieved contexts? | **0.8** (roadmap gate) |
| `answer_relevancy` | How relevant is the answer to the question? | 0.5 |
| `context_precision` | Are the retrieved contexts relevant to the question? | 0.5 |
| `context_recall` | Did retrieval find all the information needed? | 0.5 |

The evaluation exits non-zero when any metric falls below its threshold, so
it can be used as a CI gate.

## Requirements

- `ragas` and `datasets` are **lazy-imported** — the harness (and its unit
  tests) run without them. Only metric computation needs them:
  ```bash
  pip install ragas datasets
  ```
- Live mode additionally requires the app's own dependencies
  (`pip install -e .`) and a configured LLM/embedding provider (see `.env`).

## Usage

```bash
# Live mode: run the pipeline over the golden dataset (first 3 questions)
python eval/ragas_eval.py --sample 3

# Live mode: full golden dataset
python eval/ragas_eval.py

# Offline mode: evaluate pre-generated results (no live RAG service)
python eval/ragas_eval.py --offline eval/sample_results.jsonl

# Override the faithfulness threshold (e.g. for a stricter release gate)
python eval/ragas_eval.py --offline eval/sample_results.jsonl --threshold 0.85
```

Exit codes: `0` all metrics pass · `1` a metric is below threshold ·
`2` no evaluation rows were produced.

## Files

| File | Purpose |
|---|---|
| `golden_dataset.jsonl` | Golden QA pairs: `question`, `reference_answer`, `reference_contexts`. Ground truth for the evaluation. |
| `sample_results.jsonl` | Pre-generated RAG output (`question`, `answer`, `contexts`) used by the offline/CI path — a subset of the golden questions. |
| `ragas_eval.py` | CLI harness: live pipeline runner, offline merge, RAGAS metric computation, threshold gate. |
| `test_ragas_metrics.py` | Unit tests for the pure logic (dataset loading, thresholds, aggregation). RAGAS is mocked/never called, so tests run without `ragas` installed. |

## Unit tests

```bash
# From the repo root (tests use repo-relative paths)
python -m pytest eval/ -q
```

## CI

`.github/workflows/ci.yml` runs an `eval` job after tests:

```bash
pip install -e ".[dev]" ragas==0.4.3 datasets
python eval/ragas_eval.py --offline eval/sample_results.jsonl
```

The eval job runs with **`continue-on-error: true`**: RAGAS metric
computation requires an LLM/embedding provider, and in CI without provider
keys (e.g. `OPENAI_API_KEY`) the job would otherwise fail red on every PR.
Once provider secrets are configured on the repository, remove the
`continue-on-error: true` line (and the surrounding comment) to make the
eval job a required check.

## Adding a golden question

1. Append a line to `golden_dataset.jsonl`:
   ```json
   {"question": "...", "reference_answer": "...", "reference_contexts": ["..."]}
   ```
2. Regenerate live-mode results (`--sample N`), or export real pipeline
   output into a results file for offline evaluation.
3. Keep answers grounded in `reference_contexts` so faithfulness is
   measurable.
