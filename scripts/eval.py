"""End-to-end evaluation script for NZ Tax RAG.

Runs all scenarios from tests/eval/test_scenarios.yaml against a live
database and LLM, reporting retrieval precision and answer quality.

Usage:
    docker compose run --rm dev python scripts/eval.py
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import yaml

from src.db.session import get_pool
from src.llm.gateway import LLMGateway
from src.orchestrator import Orchestrator
from src.rag.embedder import GeminiEmbedder
from src.rag.retriever import HybridRetriever

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

SCENARIOS_PATH = Path(__file__).parent.parent / "tests" / "eval" / "test_scenarios.yaml"


def load_scenarios() -> list[dict[str, Any]]:
    """Load evaluation scenarios from YAML."""
    data = yaml.safe_load(SCENARIOS_PATH.read_text())
    return data["scenarios"]


async def evaluate_retrieval(
    retriever: HybridRetriever,
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate retrieval quality across all scenarios."""
    results: list[dict[str, Any]] = []

    for scenario in scenarios:
        if scenario.get("expect_out_of_scope"):
            continue

        start = time.monotonic()
        chunks = await retriever.search(scenario["question"], top_k=5)
        latency_ms = int((time.monotonic() - start) * 1000)

        found_types = {c.source_type for c in chunks}
        found_urls = [c.source_url for c in chunks]

        # Check source type matches
        expected_types = scenario.get("expected_source_types", [])
        type_hits = sum(1 for t in expected_types if t in found_types)

        # Check URL fragment matches
        expected_fragments = scenario.get("expected_url_fragments", [])
        fragment_hits = sum(
            1 for f in expected_fragments
            if any(f in url for url in found_urls)
        )

        results.append({
            "id": scenario["id"],
            "category": scenario.get("category", ""),
            "num_results": len(chunks),
            "type_precision": type_hits / len(expected_types) if expected_types else 1.0,
            "url_precision": fragment_hits / len(expected_fragments) if expected_fragments else 1.0,
            "latency_ms": latency_ms,
        })

    n = len(results)
    return {
        "total": n,
        "avg_type_precision": sum(r["type_precision"] for r in results) / n if n else 0,
        "avg_url_precision": sum(r["url_precision"] for r in results) / n if n else 0,
        "avg_latency_ms": sum(r["latency_ms"] for r in results) / n if n else 0,
        "details": results,
    }


async def evaluate_answers(
    orchestrator: Orchestrator,
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate end-to-end answer quality."""
    results: list[dict[str, Any]] = []

    for scenario in scenarios:
        start = time.monotonic()
        try:
            response = await orchestrator.ask(scenario["question"])
            latency_ms = int((time.monotonic() - start) * 1000)
        except Exception as e:
            logger.error("Error on scenario %s: %s", scenario["id"], e)
            results.append({
                "id": scenario["id"],
                "error": str(e),
                "keyword_hits": 0,
                "keyword_total": len(scenario.get("answer_keywords", [])),
            })
            continue

        answer_lower = response.answer.lower()
        keywords = scenario.get("answer_keywords", [])
        keyword_hits = sum(1 for kw in keywords if kw.lower() in answer_lower)

        results.append({
            "id": scenario["id"],
            "category": scenario.get("category", ""),
            "keyword_hits": keyword_hits,
            "keyword_total": len(keywords),
            "keyword_precision": keyword_hits / len(keywords) if keywords else 1.0,
            "num_sources": len(response.sources),
            "latency_ms": latency_ms,
            "model": response.model,
        })

    successful = [r for r in results if "error" not in r]
    return {
        "total": len(results),
        "errors": len(results) - len(successful),
        "avg_keyword_precision": (
            sum(r["keyword_precision"] for r in successful) / len(successful)
            if successful else 0
        ),
        "avg_latency_ms": (
            sum(r["latency_ms"] for r in successful) / len(successful)
            if successful else 0
        ),
        "details": results,
    }


async def main() -> None:
    """Run the full evaluation suite."""
    scenarios = load_scenarios()
    print(f"Loaded {len(scenarios)} evaluation scenarios\n")

    pool = await get_pool()
    embedder = GeminiEmbedder()
    retriever = HybridRetriever(pool, embedder)
    llm = LLMGateway()
    orchestrator = Orchestrator(retriever, llm, pool=pool)

    # Retrieval evaluation
    print("=" * 60)
    print("RETRIEVAL EVALUATION")
    print("=" * 60)
    retrieval_results = await evaluate_retrieval(retriever, scenarios)
    print(f"Scenarios evaluated: {retrieval_results['total']}")
    print(f"Avg source type precision: {retrieval_results['avg_type_precision']:.1%}")
    print(f"Avg URL fragment precision: {retrieval_results['avg_url_precision']:.1%}")
    print(f"Avg latency: {retrieval_results['avg_latency_ms']:.0f}ms")

    print("\nPer-scenario retrieval:")
    for detail in retrieval_results["details"]:
        is_pass = detail["type_precision"] == 1.0 and detail["url_precision"] == 1.0
        status = "PASS" if is_pass else "MISS"
        print(
            f"  [{status}] {detail['id']:40s} "
            f"types={detail['type_precision']:.0%} "
            f"urls={detail['url_precision']:.0%} "
            f"results={detail['num_results']} "
            f"({detail['latency_ms']}ms)"
        )

    # End-to-end evaluation
    print("\n" + "=" * 60)
    print("END-TO-END ANSWER EVALUATION")
    print("=" * 60)
    answer_results = await evaluate_answers(orchestrator, scenarios)
    print(f"Scenarios evaluated: {answer_results['total']}")
    print(f"Errors: {answer_results['errors']}")
    print(f"Avg keyword precision: {answer_results['avg_keyword_precision']:.1%}")
    print(f"Avg latency: {answer_results['avg_latency_ms']:.0f}ms")

    print("\nPer-scenario answers:")
    for detail in answer_results["details"]:
        if "error" in detail:
            print(f"  [ERR ] {detail['id']:40s} {detail['error']}")
        else:
            status = "PASS" if detail["keyword_precision"] == 1.0 else "MISS"
            print(
                f"  [{status}] {detail['id']:40s} "
                f"keywords={detail['keyword_hits']}/{detail['keyword_total']} "
                f"sources={detail['num_sources']} "
                f"({detail['latency_ms']}ms)"
            )

    from src.db.session import close_pool
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
