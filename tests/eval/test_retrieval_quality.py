"""Retrieval quality evaluation tests.

These tests require a populated database and valid GEMINI_API_KEY.
Run with: docker compose run --rm dev pytest tests/eval/ -m slow -v
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest

from src.db.session import close_pool, get_pool
from src.rag.embedder import GeminiEmbedder
from src.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="module")]


@pytest.fixture(scope="module")
async def retriever() -> AsyncIterator[HybridRetriever]:
    """Create a retriever with real DB and embedder."""
    pool = await get_pool()
    embedder = GeminiEmbedder()
    yield HybridRetriever(pool, embedder)
    await close_pool()


async def test_retrieval_returns_results(
    retriever: HybridRetriever,
    eval_scenarios: list[dict[str, Any]],
) -> None:
    """Each non-out-of-scope scenario should retrieve at least one result."""
    failures: list[str] = []

    for scenario in eval_scenarios:
        if scenario.get("expect_out_of_scope"):
            continue

        results = await retriever.search(scenario["question"], top_k=5)
        if not results:
            failures.append(f"[{scenario['id']}] No results for: {scenario['question']}")

    if failures:
        pytest.fail("Retrieval returned no results:\n" + "\n".join(failures))


async def test_retrieval_source_types(
    retriever: HybridRetriever,
    eval_scenarios: list[dict[str, Any]],
) -> None:
    """At least one expected source type should appear in top-k results."""
    failures: list[str] = []

    for scenario in eval_scenarios:
        expected_types = scenario.get("expected_source_types", [])
        if not expected_types or scenario.get("expect_out_of_scope"):
            continue

        results = await retriever.search(scenario["question"], top_k=5)
        found_types = {r.source_type for r in results}

        if not found_types.intersection(expected_types):
            failures.append(
                f"[{scenario['id']}] None of expected source_types "
                f"{expected_types} found in results: {found_types}"
            )

    if failures:
        pytest.fail(
            f"Source type mismatches ({len(failures)}):\n" + "\n".join(failures)
        )


async def test_retrieval_url_fragments(
    retriever: HybridRetriever,
    eval_scenarios: list[dict[str, Any]],
) -> None:
    """Expected URL fragments should appear in at least one result URL."""
    failures: list[str] = []

    for scenario in eval_scenarios:
        expected_fragments = scenario.get("expected_url_fragments", [])
        if not expected_fragments:
            continue

        results = await retriever.search(scenario["question"], top_k=5)
        result_urls = [r.source_url for r in results]

        for fragment in expected_fragments:
            if not any(fragment in url for url in result_urls):
                failures.append(
                    f"[{scenario['id']}] Expected URL fragment '{fragment}' not in "
                    f"any result URL: {result_urls}"
                )

    if failures:
        pytest.fail(
            f"URL fragment mismatches ({len(failures)}):\n" + "\n".join(failures)
        )
