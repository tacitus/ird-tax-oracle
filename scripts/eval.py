"""End-to-end evaluation script for NZ Tax RAG.

Runs all scenarios from tests/eval/test_scenarios.yaml against a live
database and LLM, reporting retrieval precision and answer quality.

Usage:
    docker compose run --rm dev python scripts/eval.py
"""

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any

import yaml

from src.db.session import get_pool
from src.llm.gateway import LLMGateway
from src.orchestrator import Orchestrator
from src.rag.embedder import GeminiEmbedder
from src.rag.retriever import HybridRetriever

# Matches markdown links: [text](url)
_MARKDOWN_LINK_RE = re.compile(r"\[.+?\]\(https?://[^\s)]+\)")

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
        has_citation = bool(_MARKDOWN_LINK_RE.search(response.answer))

        results.append({
            "id": scenario["id"],
            "category": scenario.get("category", ""),
            "keyword_hits": keyword_hits,
            "keyword_total": len(keywords),
            "keyword_precision": keyword_hits / len(keywords) if keywords else 1.0,
            "has_citation": has_citation,
            "num_sources": len(response.sources),
            "latency_ms": latency_ms,
            "model": response.model,
        })

    successful = [r for r in results if "error" not in r]
    cited = sum(1 for r in successful if r.get("has_citation"))
    return {
        "total": len(results),
        "errors": len(results) - len(successful),
        "avg_keyword_precision": (
            sum(r["keyword_precision"] for r in successful) / len(successful)
            if successful else 0
        ),
        "citation_rate": cited / len(successful) if successful else 0,
        "avg_latency_ms": (
            sum(r["latency_ms"] for r in successful) / len(successful)
            if successful else 0
        ),
        "details": results,
    }


async def main() -> None:
    """Run the full evaluation suite."""
    scenarios = load_scenarios()
    logger.info("Loaded %d evaluation scenarios", len(scenarios))

    pool = await get_pool()
    embedder = GeminiEmbedder()
    retriever = HybridRetriever(pool, embedder)
    llm = LLMGateway()
    orchestrator = Orchestrator(retriever, llm, pool=pool)

    # Retrieval evaluation
    logger.info("=" * 60)
    logger.info("RETRIEVAL EVALUATION")
    logger.info("=" * 60)
    retrieval_results = await evaluate_retrieval(retriever, scenarios)
    logger.info("Scenarios evaluated: %d", retrieval_results["total"])
    logger.info("Avg source type precision: %.1f%%", retrieval_results["avg_type_precision"] * 100)
    logger.info("Avg URL fragment precision: %.1f%%", retrieval_results["avg_url_precision"] * 100)
    logger.info("Avg latency: %.0fms", retrieval_results["avg_latency_ms"])

    logger.info("Per-scenario retrieval:")
    for detail in retrieval_results["details"]:
        is_pass = detail["type_precision"] == 1.0 and detail["url_precision"] == 1.0
        status = "PASS" if is_pass else "MISS"
        logger.info(
            "  [%s] %-40s types=%.0f%% urls=%.0f%% results=%d (%dms)",
            status, detail["id"],
            detail["type_precision"] * 100,
            detail["url_precision"] * 100,
            detail["num_results"],
            detail["latency_ms"],
        )

    # End-to-end evaluation
    logger.info("=" * 60)
    logger.info("END-TO-END ANSWER EVALUATION")
    logger.info("=" * 60)
    answer_results = await evaluate_answers(orchestrator, scenarios)
    logger.info("Scenarios evaluated: %d", answer_results["total"])
    logger.info("Errors: %d", answer_results["errors"])
    logger.info("Avg keyword precision: %.1f%%", answer_results["avg_keyword_precision"] * 100)
    logger.info("Citation rate: %.1f%%", answer_results["citation_rate"] * 100)
    logger.info("Avg latency: %.0fms", answer_results["avg_latency_ms"])

    logger.info("Per-scenario answers:")
    for detail in answer_results["details"]:
        if "error" in detail:
            logger.info("  [ERR ] %-40s %s", detail["id"], detail["error"])
        else:
            status = "PASS" if detail["keyword_precision"] == 1.0 else "MISS"
            cite = "cited" if detail.get("has_citation") else "NO-CITE"
            logger.info(
                "  [%s] %-40s keywords=%d/%d sources=%d %s (%dms)",
                status, detail["id"],
                detail["keyword_hits"], detail["keyword_total"],
                detail["num_sources"], cite,
                detail["latency_ms"],
            )

    from src.db.session import close_pool
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
