"""Structured output generation: JSON-mode answers with citations.

Builds a prompt that instructs the LLM to return ONLY valid JSON matching
the ``StructuredAnswer`` schema, then parses the response (plain JSON first,
markdown-fence extraction as a fallback).

The parser works with plain text responses too — the prompt enforces JSON
format. Providers that support native JSON mode (see ``generate_json`` on
``LLMProvider``) can be wired in later for extra reliability.
"""

import json
import logging
import re

from src.application.dto.structured_answer import Citation, StructuredAnswer

logger = logging.getLogger(__name__)


class StructuredOutputError(Exception):
    """Raised when the LLM response cannot be parsed into StructuredAnswer."""


def build_structured_prompt(question: str, context: list[dict[str, object]]) -> str:
    """Build a prompt instructing the LLM to return JSON with citations.

    Args:
        question: The user's question.
        context:  List of {"marker": "[1]", "content": "...",
                  "chunk_id": "...", "source": "..."} dicts.
    """
    context_block = "\n\n".join(
        f"{c['marker']} ({c.get('source', 'unknown')} / "
        f"{c.get('chunk_id', 'unknown')}) {c['content']}"
        for c in context
    )
    return (
        "You are a precise QA assistant. Answer the question using ONLY the "
        "provided context. Return ONLY valid JSON (no markdown, no prose) in "
        "this exact schema:\n"
        '{"answer": "<your answer>", '
        '"citations": [{"chunk_id": "<id>", "source": "<filename>", '
        '"page": <number or null>, "excerpt": "<short quote from the source>"}], '
        '"confidence": <0.0 to 1.0>}\n\n'
        "Use citation markers like [1], [2] in your answer text where claims "
        "come from a context snippet. citations[].chunk_id MUST be one of "
        "the chunk IDs shown in the context block; never invent an ID.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {question}"
    )


def parse_structured_response(raw: str) -> StructuredAnswer:
    """Parse the LLM response into a StructuredAnswer.

    Tries plain JSON first, then extracts from markdown code fences.
    Raises StructuredOutputError if parsing fails.
    """
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fence_match:
            try:
                data = json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError as exc:
                raise StructuredOutputError(
                    f"Invalid JSON in markdown fence: {exc}"
                ) from exc
        else:
            raise StructuredOutputError(f"Response is not valid JSON: {text[:200]}")

    try:
        return StructuredAnswer.model_validate(data)
    except Exception as exc:
        raise StructuredOutputError(f"Response does not match schema: {exc}") from exc


async def generate_structured_answer(
    llm_provider: object,
    question: str,
    chunks: list[object],
) -> StructuredAnswer:
    """Generate a structured answer with citations from retrieved chunks.

    Args:
        llm_provider: LLM provider with async generate() (and optionally
            async generate_json() for native JSON mode).
        question:     The user's question.
        chunks:       Retrieved chunks (with id, content, metadata).

    Returns:
        Parsed StructuredAnswer. Citations referencing chunk IDs that are
        not among the retrieved chunks are dropped (with a warning), so the
        result only ever cites chunks the model could actually see.

    Raises:
        StructuredOutputError: if the LLM output cannot be parsed.
    """
    context = []
    for idx, chunk in enumerate(chunks, start=1):
        filename = (
            chunk.metadata.get("filename", "unknown") if chunk.metadata else "unknown"
        )
        context.append(
            {
                "marker": f"[{idx}]",
                "content": chunk.content,
                "chunk_id": str(chunk.id),
                "source": filename,
            }
        )

    prompt = build_structured_prompt(question, context)

    generate_json = getattr(llm_provider, "generate_json", None)
    if callable(generate_json):
        try:
            raw = await generate_json(prompt)
        except Exception as exc:
            logger.warning("generate_json failed (%s); falling back to generate()", exc)
            raw = await llm_provider.generate(prompt)
    else:
        raw = await llm_provider.generate(prompt)

    parsed = parse_structured_response(raw)

    # Drop citations that reference chunks the model never saw. The model
    # is instructed to only use shown chunk IDs, but fabricated IDs must
    # not leak into the response.
    valid_chunk_ids = {str(chunk.id) for chunk in chunks}
    kept = [c for c in parsed.citations if c.chunk_id in valid_chunk_ids]
    dropped = len(parsed.citations) - len(kept)
    if dropped:
        logger.warning("Dropped %d citation(s) referencing unknown chunk_ids", dropped)
    parsed.citations = kept
    return parsed


__all__ = [
    "Citation",
    "StructuredAnswer",
    "StructuredOutputError",
    "build_structured_prompt",
    "generate_structured_answer",
    "parse_structured_response",
]
